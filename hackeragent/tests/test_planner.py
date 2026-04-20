"""Planner birim testleri."""

from __future__ import annotations

from unittest.mock import MagicMock

from hackeragent.core.llm_client import LLMReply
from hackeragent.core.planner import (
    Plan,
    PlanStep,
    Planner,
    _parse_plan_reply,
    is_complex_task,
)


def test_is_complex_task_short_input_skipped():
    assert is_complex_task("merhaba") is False
    assert is_complex_task("") is False
    assert is_complex_task("port 80") is False  # < 40 char


def test_is_complex_task_detects_pentest_keywords():
    assert is_complex_task("10.10.10.10'u tara ve zafiyetleri bul sonra exploit yaz") is True
    assert is_complex_task("kapsamlı bir bug bounty testi yap bu hedefe") is True
    assert is_complex_task("this CTF challenge needs a full writeup please") is True


def test_is_complex_task_long_input_accepted():
    long_input = " ".join(["kelime"] * 20)  # 20 kelime ama keyword yok
    assert is_complex_task(long_input) is True


def test_parse_valid_json_plan():
    raw = '''
    {
      "steps": [
        {"step": 1, "goal": "recon", "expected_tools": ["nmap", "subdomain_enum"], "success_criteria": "10+ subdomain"},
        {"step": 2, "goal": "web_discovery", "expected_tools": ["ffuf"], "success_criteria": "endpoints bulundu"}
      ]
    }
    '''
    plan = _parse_plan_reply("görev", raw)
    assert plan is not None
    assert len(plan.steps) == 2
    assert plan.steps[0].goal == "recon"
    assert "nmap" in plan.steps[0].expected_tools
    assert plan.steps[1].success_criteria == "endpoints bulundu"


def test_parse_json_wrapped_in_markdown():
    raw = '''Burada plan:
```json
{"steps": [{"step": 1, "goal": "recon", "expected_tools": []}]}
```
İşte bu.'''
    plan = _parse_plan_reply("görev", raw)
    assert plan is not None
    assert len(plan.steps) == 1


def test_parse_malformed_returns_none():
    assert _parse_plan_reply("g", "") is None
    assert _parse_plan_reply("g", "bu JSON değil") is None
    assert _parse_plan_reply("g", "{broken") is None


def test_parse_empty_steps_returns_none():
    assert _parse_plan_reply("g", '{"steps": []}') is None
    assert _parse_plan_reply("g", '{"nothing": "here"}') is None


def test_planner_skips_simple_task():
    llm = MagicMock()
    p = Planner(llm)
    result = p.plan("merhaba")
    assert result is None
    llm.chat.assert_not_called()


def test_planner_disabled_returns_none():
    llm = MagicMock()
    p = Planner(llm, enabled=False)
    result = p.plan("10.10.10.10'a kapsamlı pentest yap ve bug bounty raporu hazırla")
    assert result is None
    llm.chat.assert_not_called()


def test_planner_runs_for_complex_task():
    llm = MagicMock()
    llm.chat.return_value = LLMReply(
        content='{"steps": [{"step": 1, "goal": "recon", "expected_tools": ["nmap"]}]}'
    )
    p = Planner(llm)
    plan = p.plan("example.com için kapsamlı pentest yap ve zafiyet raporu üret")
    assert plan is not None
    assert len(plan.steps) == 1
    llm.chat.assert_called_once()


def test_planner_handles_llm_exception():
    llm = MagicMock()
    llm.chat.side_effect = Exception("LLM error")
    p = Planner(llm)
    # Exception fırlatmamalı, None dönmeli
    result = p.plan("example.com'a kapsamlı pentest yap bug bounty raporu")
    assert result is None


def test_plan_to_system_message_contains_all_steps():
    plan = Plan(
        task="test",
        steps=[
            PlanStep(step=1, goal="recon", expected_tools=["nmap"], success_criteria="port list"),
            PlanStep(step=2, goal="exploit", expected_tools=["sqlmap"]),
        ],
    )
    msg = plan.to_system_message()
    assert "recon" in msg
    assert "exploit" in msg
    assert "nmap" in msg
    assert "sqlmap" in msg
    assert "GÖREV PLANI" in msg
