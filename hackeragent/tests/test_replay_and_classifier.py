"""Tests for session replay helpers."""
from unittest.mock import MagicMock

from hackeragent.core.replay import extract_user_messages, replay_summary
from hackeragent.core.router import LLMTierClassifier


class FakeSession:
    def __init__(self, messages, session_id="test-123", target="example.com", cost=0.5):
        self.messages = messages
        self.id = session_id
        self.target = target
        self.total_cost_usd = cost


def test_extract_user_messages_basic():
    s = FakeSession([
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "answer"},
        {"role": "user", "content": "second"},
    ])
    msgs = extract_user_messages(s)
    assert msgs == ["first question", "second"]


def test_extract_user_messages_empty():
    s = FakeSession([{"role": "system", "content": "sys"}])
    assert extract_user_messages(s) == []


def test_extract_user_messages_multimodal():
    s = FakeSession([
        {"role": "user", "content": [
            {"type": "text", "text": "part1"},
            {"type": "text", "text": "part2"},
        ]},
    ])
    msgs = extract_user_messages(s)
    assert msgs == ["part1\npart2"]


def test_extract_user_messages_filters_empty():
    s = FakeSession([
        {"role": "user", "content": ""},
        {"role": "user", "content": "   "},
        {"role": "user", "content": "real"},
    ])
    msgs = extract_user_messages(s)
    assert msgs == ["real"]


def test_replay_summary_contains_session_id():
    s = FakeSession([{"role": "user", "content": "q"}], session_id="abc-xyz")
    txt = replay_summary(s)
    assert "abc-xyz" in txt
    assert "example.com" in txt


def test_llm_classifier_returns_cheap():
    fake_llm = MagicMock()
    fake_reply = MagicMock()
    fake_reply.content = "cheap"
    fake_llm.chat.return_value = fake_reply
    c = LLMTierClassifier(fake_llm, cheap_model="cheap-m")
    msgs = [{"role": "user", "content": "merhaba"}]
    assert c.classify(msgs) == "cheap"


def test_llm_classifier_returns_premium():
    fake_llm = MagicMock()
    fake_reply = MagicMock()
    fake_reply.content = "premium\n"
    fake_llm.chat.return_value = fake_reply
    c = LLMTierClassifier(fake_llm, cheap_model="cheap-m")
    msgs = [{"role": "user", "content": "exploit for CVE-2021-1234"}]
    assert c.classify(msgs) == "premium"


def test_llm_classifier_invalid_response_defaults_standard():
    fake_llm = MagicMock()
    fake_reply = MagicMock()
    fake_reply.content = "random garbage"
    fake_llm.chat.return_value = fake_reply
    c = LLMTierClassifier(fake_llm, cheap_model="cheap-m")
    msgs = [{"role": "user", "content": "task"}]
    assert c.classify(msgs) == "standard"


def test_llm_classifier_handles_exception():
    fake_llm = MagicMock()
    fake_llm.chat.side_effect = Exception("network error")
    c = LLMTierClassifier(fake_llm, cheap_model="cheap-m")
    msgs = [{"role": "user", "content": "task"}]
    assert c.classify(msgs) == "standard"


def test_llm_classifier_caches_result():
    fake_llm = MagicMock()
    fake_reply = MagicMock()
    fake_reply.content = "standard"
    fake_llm.chat.return_value = fake_reply
    c = LLMTierClassifier(fake_llm, cheap_model="cheap-m", cache_ttl=60)
    msgs = [{"role": "user", "content": "same task"}]
    c.classify(msgs)
    c.classify(msgs)
    c.classify(msgs)
    # LLM sadece 1 kez çağrılmalı (cache hit)
    assert fake_llm.chat.call_count == 1


def test_llm_classifier_empty_message_returns_standard():
    fake_llm = MagicMock()
    c = LLMTierClassifier(fake_llm, cheap_model="cheap-m")
    assert c.classify([]) == "standard"
    assert c.classify([{"role": "user", "content": ""}]) == "standard"
    fake_llm.chat.assert_not_called()


def test_model_router_uses_classifier_when_present():
    from hackeragent.core.router import ModelRouter, ModelTiers
    tiers = ModelTiers(cheap="c", standard="s", premium="p")
    fake_classifier = MagicMock()
    fake_classifier.classify.return_value = "premium"
    r = ModelRouter(tiers=tiers, enabled=True, llm_classifier=fake_classifier)
    msgs = [{"role": "user", "content": "task"}]
    assert r.pick(msgs) == "p"


def test_model_router_falls_back_on_classifier_error():
    from hackeragent.core.router import ModelRouter, ModelTiers
    tiers = ModelTiers(cheap="c", standard="s", premium="p")
    fake_classifier = MagicMock()
    fake_classifier.classify.side_effect = RuntimeError("boom")
    r = ModelRouter(tiers=tiers, enabled=True, llm_classifier=fake_classifier)
    # Heuristik fallback — kısa greeting → cheap
    msgs = [{"role": "user", "content": "merhaba"}]
    assert r.pick(msgs) in ("c", "s")
