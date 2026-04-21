"""Tests for LLM client prompt caching."""
from hackeragent.core.llm_client import _apply_prompt_cache


def test_empty_messages_returns_empty():
    assert _apply_prompt_cache([]) == []


def test_first_system_message_gets_cache_control():
    msgs = [
        {"role": "system", "content": "You are helpful"},
        {"role": "user", "content": "hi"},
    ]
    out = _apply_prompt_cache(msgs)
    assert out[0]["role"] == "system"
    content = out[0]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[0]["text"] == "You are helpful"
    assert content[0]["cache_control"] == {"type": "ephemeral"}
    # User message unchanged
    assert out[1] == {"role": "user", "content": "hi"}


def test_two_system_messages_both_cached():
    msgs = [
        {"role": "system", "content": "sys1"},
        {"role": "system", "content": "sys2 workflow"},
        {"role": "user", "content": "hi"},
    ]
    out = _apply_prompt_cache(msgs)
    assert isinstance(out[0]["content"], list)
    assert isinstance(out[1]["content"], list)
    assert out[0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert out[1]["content"][0]["cache_control"] == {"type": "ephemeral"}


def test_third_system_message_not_cached():
    msgs = [
        {"role": "system", "content": "sys1"},
        {"role": "system", "content": "sys2"},
        {"role": "system", "content": "sys3"},
        {"role": "user", "content": "hi"},
    ]
    out = _apply_prompt_cache(msgs)
    # Third system stays as string (only first 2 cached)
    assert out[2]["content"] == "sys3"


def test_empty_system_content_not_modified():
    msgs = [{"role": "system", "content": ""}, {"role": "user", "content": "hi"}]
    out = _apply_prompt_cache(msgs)
    # Empty string → skip caching, keep original
    assert out[0]["content"] == ""


def test_user_and_assistant_never_cached():
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    out = _apply_prompt_cache(msgs)
    assert out[0]["content"] == "hi"
    assert out[1]["content"] == "hello"
