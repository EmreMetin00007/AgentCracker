"""Config validator — startup'ta config.yaml şemasını doğrular.

Amaç: yanlış / eksik konfigürasyonu erken (çalışma öncesi) yakalamak.
Kullanım:
    errors, warnings = validate_config(config.data)
    if errors:  # fatal
        for e in errors: ...

Bu sadece "obvious" hataları yakalar; tip uyumu ve değer aralığı.
Runtime'da ayrıca `core/config.py` `.get()` ile default'a düşer.
"""

from __future__ import annotations

from typing import Any

# (path, expected_type, human_hint)
_SCHEMA: list[tuple[str, type | tuple[type, ...], str]] = [
    ("llm.provider", str, "openrouter"),
    ("llm.base_url", str, "https://openrouter.ai/api/v1"),
    ("llm.max_tokens", int, "4096"),
    ("llm.temperature", (int, float), "0-2 arası"),
    ("llm.timeout_seconds", int, "saniye"),
    ("llm.max_tool_iterations", int, "25"),
    ("llm.max_session_cost_usd", (int, float), "0 = sınırsız"),
    ("llm.compression_threshold_chars", int, "40000"),
    ("llm.compression_keep_tail", int, "10"),
    ("llm.planner_max_steps", int, "6"),
    ("safety.rate_limit_rps", (int, float), "RPS"),
    ("safety.parallel_max_workers", int, "paralel tool sayısı"),
]

_BOOL_FIELDS = [
    "llm.streaming",
    "llm.router_enabled",
    "llm.self_reflection_enabled",
    "llm.tool_cache_enabled",
    "llm.compression_enabled",
    "llm.planner_enabled",
    "llm.vision_enabled",
    "rag.auto_enrich",
    "safety.parallel_tool_execution",
    "safety.scope_enforcement",
]


def _get(data: dict, path: str) -> Any:
    node: Any = data
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def validate_config(data: dict) -> tuple[list[str], list[str]]:
    """Config'i doğrula. (errors, warnings) döner.

    errors → fatal, startup'ı engellemeli.
    warnings → kullanıcıya gösterilmeli ama devam edilebilir.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # 1) Tip kontrolü
    for path, expected, hint in _SCHEMA:
        val = _get(data, path)
        if val is None:
            continue  # default'a düşecek
        if not isinstance(val, expected):
            exp_name = getattr(expected, "__name__", str(expected))
            errors.append(f"{path}: bekleniyor {exp_name} ({hint}), gelen {type(val).__name__}={val!r}")

    # 2) Bool alanları
    for path in _BOOL_FIELDS:
        val = _get(data, path)
        if val is None:
            continue
        if not isinstance(val, bool):
            errors.append(f"{path}: bekleniyor bool (true/false), gelen {type(val).__name__}={val!r}")

    # 3) Mantıksal kontroller
    temp = _get(data, "llm.temperature")
    if isinstance(temp, (int, float)) and not (0.0 <= float(temp) <= 2.0):
        errors.append(f"llm.temperature: 0-2 arasında olmalı, gelen {temp}")

    max_tokens = _get(data, "llm.max_tokens")
    if isinstance(max_tokens, int) and max_tokens < 1:
        errors.append(f"llm.max_tokens: >=1 olmalı, gelen {max_tokens}")

    iters = _get(data, "llm.max_tool_iterations")
    if isinstance(iters, int) and iters < 1:
        errors.append(f"llm.max_tool_iterations: >=1 olmalı, gelen {iters}")

    workers = _get(data, "safety.parallel_max_workers")
    if isinstance(workers, int) and workers < 1:
        errors.append(f"safety.parallel_max_workers: >=1 olmalı, gelen {workers}")

    # 4) MCP server config doğrula
    servers = _get(data, "mcp_servers") or {}
    if not isinstance(servers, dict):
        errors.append(f"mcp_servers: bekleniyor dict, gelen {type(servers).__name__}")
    else:
        for name, cfg in servers.items():
            if not isinstance(cfg, dict):
                errors.append(f"mcp_servers.{name}: bekleniyor dict")
                continue
            if cfg.get("enabled", True):
                cmd = cfg.get("command")
                if not cmd or not isinstance(cmd, str):
                    errors.append(f"mcp_servers.{name}.command: string olmalı (enabled ise)")
                args = cfg.get("args")
                if args is not None and not isinstance(args, list):
                    errors.append(f"mcp_servers.{name}.args: list olmalı")

    # 5) Scope format kontrolü (warning)
    scope_list = _get(data, "safety.scope") or []
    if isinstance(scope_list, list):
        for s in scope_list:
            if not isinstance(s, str):
                errors.append(f"safety.scope: her entry string olmalı, gelen {type(s).__name__}={s!r}")
            elif not s.strip():
                warnings.append("safety.scope: boş string entry görmezden geliniyor")

    # 6) Model ismi uyarıları (warning)
    orch_model = _get(data, "llm.models.orchestrator")
    if isinstance(orch_model, str) and "/" not in orch_model and orch_model:
        warnings.append(
            f"llm.models.orchestrator='{orch_model}' OpenRouter formatında değil "
            f"(bekleniyor: 'provider/model-name')"
        )

    # 7) Bütçe uyarısı
    budget = _get(data, "llm.max_session_cost_usd")
    if isinstance(budget, (int, float)) and float(budget) < 0:
        errors.append(f"llm.max_session_cost_usd: <0 olamaz, gelen {budget}")

    return errors, warnings


def format_validation_result(errors: list[str], warnings: list[str]) -> str:
    """Sonuçları insan-okunur formatla."""
    lines: list[str] = []
    if errors:
        lines.append(f"✗ Config validation — {len(errors)} HATA:")
        for e in errors:
            lines.append(f"  • {e}")
    if warnings:
        lines.append(f"⚠ Config validation — {len(warnings)} uyarı:")
        for w in warnings:
            lines.append(f"  • {w}")
    if not errors and not warnings:
        lines.append("✓ Config valid")
    return "\n".join(lines)
