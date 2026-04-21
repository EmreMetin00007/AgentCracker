"""Tests for config validator."""
from hackeragent.core.config_validator import validate_config, format_validation_result


def test_valid_config_passes():
    cfg = {
        "llm": {
            "provider": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "max_tokens": 4096,
            "temperature": 0.3,
            "timeout_seconds": 120,
            "max_tool_iterations": 25,
            "max_session_cost_usd": 5.0,
            "streaming": True,
            "router_enabled": True,
            "models": {"orchestrator": "qwen/qwen3.6-plus"},
        },
        "safety": {
            "rate_limit_rps": 10,
            "parallel_max_workers": 5,
            "parallel_tool_execution": True,
            "scope": ["10.10.10.0/24"],
        },
        "mcp_servers": {
            "kali-tools": {"enabled": True, "command": "python3", "args": ["x.py"]},
        },
    }
    errors, warnings = validate_config(cfg)
    assert errors == []


def test_wrong_type_error():
    cfg = {"llm": {"max_tokens": "not-an-int"}}
    errors, _ = validate_config(cfg)
    assert any("llm.max_tokens" in e for e in errors)


def test_temperature_out_of_range():
    cfg = {"llm": {"temperature": 5.0}}
    errors, _ = validate_config(cfg)
    assert any("temperature" in e for e in errors)


def test_negative_budget_error():
    cfg = {"llm": {"max_session_cost_usd": -1.0}}
    errors, _ = validate_config(cfg)
    assert any("max_session_cost_usd" in e for e in errors)


def test_bool_field_wrong_type():
    cfg = {"llm": {"streaming": "yes"}}
    errors, _ = validate_config(cfg)
    assert any("streaming" in e for e in errors)


def test_mcp_server_missing_command():
    cfg = {"mcp_servers": {"kali-tools": {"enabled": True}}}
    errors, _ = validate_config(cfg)
    assert any("kali-tools.command" in e for e in errors)


def test_disabled_server_skips_validation():
    cfg = {"mcp_servers": {"kali-tools": {"enabled": False}}}
    errors, _ = validate_config(cfg)
    assert not any("kali-tools" in e for e in errors)


def test_zero_max_tokens_error():
    cfg = {"llm": {"max_tokens": 0}}
    errors, _ = validate_config(cfg)
    assert any("max_tokens" in e for e in errors)


def test_parallel_workers_zero_error():
    cfg = {"safety": {"parallel_max_workers": 0}}
    errors, _ = validate_config(cfg)
    assert any("parallel_max_workers" in e for e in errors)


def test_empty_config_no_errors():
    errors, warnings = validate_config({})
    assert errors == []


def test_model_name_warning():
    cfg = {"llm": {"models": {"orchestrator": "qwen3"}}}
    errors, warnings = validate_config(cfg)
    assert errors == []
    assert any("provider/model" in w for w in warnings)


def test_format_result_with_errors():
    txt = format_validation_result(["err1", "err2"], ["warn1"])
    assert "HATA" in txt
    assert "err1" in txt
    assert "warn1" in txt


def test_format_result_empty_clean():
    txt = format_validation_result([], [])
    assert "valid" in txt.lower()
