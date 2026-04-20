"""Orchestrator entegrasyon testi — tüm harici bağımlılıklar mock'lu.

Doğrulanan akış:
  1. ModelRouter doğru tier'ı seçiyor ve LLMClient.chat'e 'model' param'ı geçiyor
  2. RAG enrichment çağrılıyor ve session'a system mesajı enjekte ediliyor
  3. Tool fail durumunda self-reflection nudge'ı ekleniyor, bir sonraki tur cheap'e gidiyor
  4. CircuitBreaker paylaşılan instance olarak ToolRouter'a geçiyor
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hackeragent.core.config import Config
from hackeragent.core.llm_client import LLMReply


def _build_config(**overrides) -> Config:
    data = {
        "llm": {
            "openrouter_api_key": "sk-test-fake",
            "base_url": "https://mock/",
            "models": {
                "orchestrator": "STD-MODEL",
                "exploit_gen": "PREM-MODEL",
                "cheap": "CHEAP-MODEL",
                "premium": "PREM-MODEL",
            },
            "max_tokens": 100,
            "temperature": 0.3,
            "timeout_seconds": 5,
            "max_tool_iterations": 3,
            "streaming": False,
            "router_enabled": True,
            "self_reflection_enabled": True,
        },
        "rag": {"auto_enrich": True},
        "safety": {"scope_enforcement": False, "scope": []},
        "mcp_servers": {},
        "logging": {"level": "WARNING", "file": ""},
    }
    data.update(overrides)
    return Config(data=data)


@pytest.fixture
def orch():
    """Patch edilmiş Orchestrator — MCP başlatılmaz, LLM mock'lanır."""
    from hackeragent.core.orchestrator import Orchestrator

    cfg = _build_config()
    with patch("hackeragent.core.orchestrator.MCPManager") as MockMCP, \
         patch("hackeragent.core.orchestrator.build_system_prompt", return_value="SYS"):
        mcp_inst = MagicMock()
        mcp_inst.start = MagicMock()
        mcp_inst.stop = MagicMock()
        mcp_inst.list_tools = MagicMock(return_value=[])
        mcp_inst.active_servers = MagicMock(return_value=["kali-tools"])
        mcp_inst.call_tool = MagicMock(return_value="")
        MockMCP.return_value = mcp_inst

        o = Orchestrator(config=cfg)
        o.llm = MagicMock()
        yield o


def test_router_picks_cheap_tier_for_short_greeting(orch):
    """Kısa selam → cheap model LLMClient.chat'e geçirilmeli."""
    orch.llm.chat.return_value = LLMReply(content="merhaba!", tool_calls=[], cost_usd=0.001)
    orch.ask("merhaba")
    # chat çağrıldı, model="CHEAP-MODEL"
    args, kwargs = orch.llm.chat.call_args
    assert kwargs.get("model") == "CHEAP-MODEL"


def test_router_picks_premium_tier_for_exploit_request(orch):
    orch.llm.chat.return_value = LLMReply(content="exploit taslağı...", tool_calls=[], cost_usd=0.01)
    orch.ask("bu SQLi için exploit PoC yazar mısın")
    args, kwargs = orch.llm.chat.call_args
    assert kwargs.get("model") == "PREM-MODEL"


def test_rag_enrichment_injects_system_message(orch):
    """RAG non-None dönerse user mesajından önce system ctx eklenmeli."""
    orch.llm.chat.return_value = LLMReply(content="ok", tool_calls=[], cost_usd=0.0)
    with patch("hackeragent.core.orchestrator.enrich_from_rag_and_memory",
               return_value="### RAG: CVE-2024 ilgili"):
        orch.ask("nginx açıkları var mı")
    # messages: [system_prompt, system(RAG), user, assistant]
    msgs = orch.session.messages
    roles = [m["role"] for m in msgs]
    assert roles[:3] == ["system", "system", "user"]
    assert "RAG" in msgs[1]["content"]


def test_rag_enrichment_skipped_when_disabled(orch):
    orch.rag_enrich_enabled = False
    orch.llm.chat.return_value = LLMReply(content="ok", tool_calls=[], cost_usd=0.0)
    with patch("hackeragent.core.orchestrator.enrich_from_rag_and_memory") as mock_rag:
        orch.ask("test")
    mock_rag.assert_not_called()


def test_rag_returns_none_no_system_injected(orch):
    orch.llm.chat.return_value = LLMReply(content="ok", tool_calls=[], cost_usd=0.0)
    with patch("hackeragent.core.orchestrator.enrich_from_rag_and_memory", return_value=None):
        orch.ask("test")
    roles = [m["role"] for m in orch.session.messages]
    # system_prompt, user, assistant
    assert roles == ["system", "user", "assistant"]


def test_self_reflection_nudge_added_on_tool_failure(orch):
    """Tool HATA ile dönerse REFLECT system message eklenmeli, sonraki tur cheap'e gitmeli."""
    # 1. tur: tool_call döndür
    reply1 = LLMReply(
        content="",
        tool_calls=[{"id": "c1", "name": "kali-tools__nmap", "arguments": {"target": "1.2.3.4"}}],
        cost_usd=0.001,
    )
    # 2. tur: text-only finish
    reply2 = LLMReply(content="tamam farklı deneyeceğim", tool_calls=[], cost_usd=0.001)
    orch.llm.chat.side_effect = [reply1, reply2]

    # Tool fail döndür
    orch.start()  # ToolRouter'ı init et
    orch.router.execute = MagicMock(return_value="HATA: nmap timeout")

    with patch("hackeragent.core.orchestrator.enrich_from_rag_and_memory", return_value=None):
        orch.ask("portları tara 1.2.3.4")

    # REFLECT system mesajı eklenmiş mi?
    contents = [m.get("content", "") for m in orch.session.messages if m.get("role") == "system"]
    assert any("REFLECT" in c for c in contents), f"No REFLECT in system messages: {contents}"

    # 2. chat çağrısı cheap model'a yönlenmeli (force_cheap_next)
    call_args_list = orch.llm.chat.call_args_list
    assert len(call_args_list) == 2
    second_call_model = call_args_list[1].kwargs.get("model")
    assert second_call_model == "CHEAP-MODEL", f"Beklenen CHEAP-MODEL, alındı: {second_call_model}"


def test_self_reflection_disabled_no_nudge(orch):
    orch.reflection_enabled = False
    reply1 = LLMReply(
        content="",
        tool_calls=[{"id": "c1", "name": "x__y", "arguments": {}}],
        cost_usd=0.001,
    )
    reply2 = LLMReply(content="done", tool_calls=[], cost_usd=0.001)
    orch.llm.chat.side_effect = [reply1, reply2]
    orch.start()
    orch.router.execute = MagicMock(return_value="HATA: boom")
    with patch("hackeragent.core.orchestrator.enrich_from_rag_and_memory", return_value=None):
        orch.ask("test")
    contents = [m.get("content", "") for m in orch.session.messages if m.get("role") == "system"]
    assert not any("REFLECT" in c for c in contents)


def test_breaker_shared_between_orchestrator_and_tool_router(orch):
    """Orchestrator'daki breaker ile ToolRouter'dakinin aynı instance olduğunu doğrula."""
    orch.start()
    assert orch.router.breaker is orch.breaker
