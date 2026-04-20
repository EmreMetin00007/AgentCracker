"""LLM client — 'No endpoints' fallback + bad tool extraction testleri."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from hackeragent.core.llm_client import (
    LLMClient,
    _drop_tool,
    _extract_bad_tool,
)


def test_extract_bad_tool_from_error_message():
    err = '{"error":{"message":"No endpoints found that support tool use. Try disabling \\"kali-tools__parallel_recon\\". To learn more...","code":404}}'
    assert _extract_bad_tool(err) == "kali-tools__parallel_recon"


def test_extract_bad_tool_no_match():
    assert _extract_bad_tool("unrelated error") is None
    assert _extract_bad_tool("") is None
    assert _extract_bad_tool(None) is None  # type: ignore[arg-type]


def test_drop_tool_removes_by_name():
    tools = [
        {"type": "function", "function": {"name": "a__x"}},
        {"type": "function", "function": {"name": "b__y"}},
        {"type": "function", "function": {"name": "c__z"}},
    ]
    filtered = _drop_tool(tools, "b__y")
    names = [t["function"]["name"] for t in filtered]
    assert names == ["a__x", "c__z"]


def test_drop_tool_no_match_keeps_all():
    tools = [{"type": "function", "function": {"name": "a__x"}}]
    assert _drop_tool(tools, "z__z") == tools


def _mock_response(status: int, text: str = "", json_data: dict | None = None):
    m = MagicMock(spec=requests.Response)
    m.status_code = status
    m.text = text
    m.json.return_value = json_data or {}
    if status >= 400:
        m.raise_for_status.side_effect = requests.exceptions.HTTPError(response=m)
    else:
        m.raise_for_status.return_value = None
    return m


def test_chat_404_no_endpoints_retries_with_tool_excluded():
    """404 'No endpoints' hatası → problematik tool'u exclude et + retry."""
    client = LLMClient(api_key="x", model="qwen/qwen3.6-plus", timeout=5)
    tools = [
        {"type": "function", "function": {"name": "ok__tool", "parameters": {"type": "object"}}},
        {"type": "function", "function": {"name": "bad__tool", "parameters": {"type": "object"}}},
    ]
    err_text = '{"error":{"message":"No endpoints found. Try disabling \\"bad__tool\\"","code":404}}'
    ok_resp = _mock_response(200, json_data={
        "choices": [{"message": {"content": "OK", "tool_calls": []},
                     "finish_reason": "stop"}],
        "usage": {"cost": 0.001},
    })
    with patch("hackeragent.core.llm_client.requests.post") as mpost:
        mpost.side_effect = [_mock_response(404, text=err_text), ok_resp]
        reply = client.chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=tools,
            retries=3,
        )
    assert reply.content == "OK"
    # 2 kez çağrıldı: 1. fail, 2. retry (bad__tool exclude)
    assert mpost.call_count == 2
    # 2. çağrının payload'ında bad__tool YOK, ok__tool VAR
    second_payload = mpost.call_args_list[1].kwargs["json"]
    tool_names = [t["function"]["name"] for t in second_payload["tools"]]
    assert "bad__tool" not in tool_names
    assert "ok__tool" in tool_names


def test_chat_404_without_tool_name_falls_back_to_no_tools():
    """404 ama tool adı parse edilemezse → tools'suz retry."""
    client = LLMClient(api_key="x", model="qwen/qwen3.6-plus", timeout=5)
    tools = [{"type": "function", "function": {"name": "t__x", "parameters": {"type": "object"}}}]
    err_text = '{"error":{"message":"No endpoints found. Unrelated message","code":404}}'
    ok_resp = _mock_response(200, json_data={
        "choices": [{"message": {"content": "text only", "tool_calls": []},
                     "finish_reason": "stop"}],
        "usage": {},
    })
    with patch("hackeragent.core.llm_client.requests.post") as mpost:
        mpost.side_effect = [_mock_response(404, text=err_text), ok_resp]
        reply = client.chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=tools,
            retries=3,
        )
    assert reply.content == "text only"
    # 2. çağrıda tools YOK
    second_payload = mpost.call_args_list[1].kwargs["json"]
    assert "tools" not in second_payload
    assert "tool_choice" not in second_payload
