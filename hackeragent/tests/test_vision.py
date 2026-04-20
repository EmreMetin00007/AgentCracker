"""Vision / multimodal helper birim testleri."""

from __future__ import annotations

import json

from hackeragent.core.vision import (
    extract_image_from_tool_result,
    model_supports_vision,
    to_multimodal_tool_message,
)


def test_model_supports_vision_claude():
    assert model_supports_vision("anthropic/claude-3.5-sonnet") is True
    assert model_supports_vision("anthropic/claude-3-opus") is True


def test_model_supports_vision_openai():
    assert model_supports_vision("openai/gpt-4o") is True
    assert model_supports_vision("openai/gpt-4o-mini") is True
    assert model_supports_vision("openai/gpt-5.2") is True


def test_model_supports_vision_gemini_qwen():
    assert model_supports_vision("google/gemini-2.5-flash") is True
    assert model_supports_vision("google/gemini-3-pro") is True
    assert model_supports_vision("qwen/qwen-2.5-vl-72b") is True


def test_model_no_vision_for_text_only():
    assert model_supports_vision("qwen/qwen3.6-plus") is False
    assert model_supports_vision("nousresearch/hermes-4-405b") is False
    assert model_supports_vision("mistralai/mistral-large") is False


def test_extract_image_plain_text_returns_none():
    data_url, summary = extract_image_from_tool_result("port 80 open\nport 443 open")
    assert data_url is None
    assert "port 80" in summary


def test_extract_image_json_without_image():
    res = json.dumps({"findings": ["CVE-X"], "count": 1})
    data_url, summary = extract_image_from_tool_result(res)
    assert data_url is None


def test_extract_image_from_screenshot_json():
    res = json.dumps({
        "url": "https://example.com",
        "title": "Example",
        "path": "/tmp/x.png",
        "size_bytes": 1234,
        "base64": "iVBORw0KGgo",
        "data_url": "data:image/png;base64,iVBORw0KGgo",
    })
    data_url, summary = extract_image_from_tool_result(res)
    assert data_url == "data:image/png;base64,iVBORw0KGgo"
    assert "example.com" in summary
    assert "Example" in summary


def test_to_multimodal_with_image():
    res = json.dumps({
        "url": "https://example.com",
        "title": "Login Page",
        "data_url": "data:image/png;base64,AAA",
    })
    msg = to_multimodal_tool_message("call_1", res, enabled=True)
    assert msg["role"] == "tool"
    assert msg["tool_call_id"] == "call_1"
    assert isinstance(msg["content"], list)
    assert msg["content"][0]["type"] == "text"
    assert msg["content"][1]["type"] == "image_url"
    assert msg["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_to_multimodal_disabled_returns_plain_text():
    res = json.dumps({"data_url": "data:image/png;base64,AAA", "url": "x"})
    msg = to_multimodal_tool_message("c1", res, enabled=False)
    assert isinstance(msg["content"], str)


def test_to_multimodal_no_image_returns_plain():
    msg = to_multimodal_tool_message("c1", "port 80 open", enabled=True)
    assert isinstance(msg["content"], str)
    assert msg["content"] == "port 80 open"
