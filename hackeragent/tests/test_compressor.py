"""Compressor birim testleri (LLM mock'lu)."""

from __future__ import annotations

from unittest.mock import MagicMock

from hackeragent.core.compressor import Compressor, total_chars
from hackeragent.core.llm_client import LLMReply


def _make_msgs(n_tool: int = 20, chars_each: int = 3000) -> list[dict]:
    msgs = [{"role": "system", "content": "SYS"}]
    for i in range(n_tool):
        msgs.append({"role": "user", "content": f"user msg {i}"})
        msgs.append({"role": "assistant", "content": ""})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": "A" * chars_each})
    return msgs


def test_total_chars_counts_strings_and_multimodal():
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "tool", "content": [
            {"type": "text", "text": "some text"},
            {"type": "image_url", "image_url": {"url": "data:..."}},
        ]},
    ]
    assert total_chars(msgs) == len("hello") + len("some text")


def test_should_not_compress_under_threshold():
    llm = MagicMock()
    c = Compressor(llm, threshold_chars=100_000, keep_tail=5)
    msgs = _make_msgs(n_tool=3, chars_each=500)
    assert c.should_compress(msgs) is False


def test_should_compress_over_threshold():
    llm = MagicMock()
    c = Compressor(llm, threshold_chars=10_000, keep_tail=5)
    msgs = _make_msgs(n_tool=20, chars_each=1000)  # > 60k
    assert c.should_compress(msgs) is True


def test_disabled_never_compresses():
    llm = MagicMock()
    c = Compressor(llm, threshold_chars=1, keep_tail=1, enabled=False)
    msgs = _make_msgs(n_tool=10)
    assert c.should_compress(msgs) is False


def test_compress_replaces_middle_with_summary():
    llm = MagicMock()
    llm.chat.return_value = LLMReply(
        content="### Özet\n- 3 port açık\n- nmap yapıldı",
        cost_usd=0.0015,
    )
    c = Compressor(llm, threshold_chars=10_000, keep_tail=4)
    msgs = _make_msgs(n_tool=10, chars_each=2000)
    before_count = len(msgs)
    before_chars = total_chars(msgs)

    result = c.compress(msgs)
    assert result.compressed is True
    assert result.removed_count > 0
    assert result.before_chars == before_chars
    assert result.after_chars < before_chars
    # Yeni: LLM cost_usd CompressionResult'ta var
    assert result.llm_cost_usd == 0.0015
    # Mesaj sayısı azaldı
    assert len(msgs) < before_count
    # İlk mesaj system prompt
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "SYS"
    # Compression özeti system role'de
    assert any("SIKIŞTIRILMIŞ" in (m.get("content") or "") for m in msgs)


def test_compress_preserves_tail():
    llm = MagicMock()
    llm.chat.return_value = LLMReply(content="ÖZET")
    c = Compressor(llm, threshold_chars=10_000, keep_tail=6)
    msgs = _make_msgs(n_tool=20, chars_each=500)
    tail_contents_before = [m.get("content") for m in msgs[-6:]]
    c.compress(msgs)
    tail_after = [m.get("content") for m in msgs[-6:]]
    assert tail_contents_before == tail_after


def test_compress_handles_llm_failure():
    llm = MagicMock()
    llm.chat.side_effect = Exception("LLM down")
    c = Compressor(llm, threshold_chars=10_000, keep_tail=4)
    msgs = _make_msgs(n_tool=20, chars_each=1000)
    before_count = len(msgs)
    result = c.compress(msgs)
    # LLM hatası → sıkıştırılmadı ama exception da fırlatmadı
    assert result.compressed is False
    assert len(msgs) == before_count
