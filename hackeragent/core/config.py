"""Config yükleme katmanı.

Öncelik sırası:
  1. Environment variables (en yüksek)
  2. ~/.hackeragent/config.yaml (user override)
  3. <project>/config.yaml (repo varsayılanı)
  4. Built-in DEFAULTS (en düşük)

Ayrıca `.env` dosyasını (project root veya CWD) otomatik yükler.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

# ─── .env loader ────────────────────────────────────────────────────────────
def _load_dotenv(path: Path) -> None:
    """Basit .env parser — python-dotenv opsiyonel dependency."""
    if not path.is_file():
        return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        pass


# Repo kökü: hackeragent paketi <REPO>/hackeragent/core/config.py içinde
REPO_ROOT = Path(__file__).resolve().parents[2]
_load_dotenv(REPO_ROOT / ".env")
_load_dotenv(Path.cwd() / ".env")


# ─── Paths ──────────────────────────────────────────────────────────────────
HACKERAGENT_HOME = Path(
    os.environ.get("HACKERAGENT_HOME", Path.home() / ".hackeragent")
).expanduser()
HACKERAGENT_HOME.mkdir(parents=True, exist_ok=True)
os.environ["HACKERAGENT_HOME"] = str(HACKERAGENT_HOME)  # MCP servers'a miras

LOG_DIR = HACKERAGENT_HOME / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT_PATH = REPO_ROOT / "system_prompt.md"
# Legacy fallback (eski projelerde hala CLAUDE.md olabilir)
if not SYSTEM_PROMPT_PATH.exists() and (REPO_ROOT / "CLAUDE.md").exists():
    SYSTEM_PROMPT_PATH = REPO_ROOT / "CLAUDE.md"

RULES_DIR = REPO_ROOT / "rules"
SKILLS_DIR = REPO_ROOT / "skills"
WORKFLOWS_DIR = REPO_ROOT / "workflows"
MCP_SERVERS_DIR = REPO_ROOT / "mcp-servers"


# ─── Defaults ───────────────────────────────────────────────────────────────
DEFAULTS: dict[str, Any] = {
    "hackeragent": {
        "version": "3.0",
        "data_dir": str(HACKERAGENT_HOME),
    },
    "llm": {
        "provider": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "openrouter_api_key": "",  # config.yaml'dan override edilebilir
        "models": {
            "orchestrator": "qwen/qwen3.6-plus",
            "analyzer": "qwen/qwen3.6-plus",
            "exploit_gen": "nousresearch/hermes-4-405b",
            "report": "qwen/qwen3.6-plus",
        },
        "max_tokens": 4096,
        "temperature": 0.3,
        "timeout_seconds": 120,
        "max_tool_iterations": 25,
    },
    "mcp_servers": {
        "kali-tools": {
            "command": "python3",
            "args": [str(MCP_SERVERS_DIR / "mcp-kali-tools" / "server.py")],
            "enabled": True,
        },
        "memory-server": {
            "command": "python3",
            "args": [str(MCP_SERVERS_DIR / "mcp-memory-server" / "server.py")],
            "enabled": True,
        },
        "ctf-platform": {
            "command": "python3",
            "args": [str(MCP_SERVERS_DIR / "mcp-ctf-platform" / "server.py")],
            "enabled": True,
            "env": {
                "CTFD_URL": "",
                "CTFD_TOKEN": "",
                "HTB_TOKEN": "",
                "THM_TOKEN": "",
            },
        },
        "telemetry": {
            "command": "python3",
            "args": [str(MCP_SERVERS_DIR / "mcp-telemetry" / "server.py")],
            "enabled": True,
        },
        "rag-engine": {
            "command": "python3",
            "args": [str(MCP_SERVERS_DIR / "mcp-rag-engine" / "server.py")],
            "enabled": True,
        },
    },
    "safety": {
        "require_approval": ["exploit", "lateral_movement", "flag_submit"],
        "rate_limit_rps": 10,
    },
    "logging": {
        "level": "INFO",
        "file": str(LOG_DIR / "agent.log"),
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursive dict merge; override değerleri baseyi değiştirir."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _load_yaml(path: Path) -> dict:
    if not path.is_file() or yaml is None:
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


@dataclass
class Config:
    """Birleşik konfigürasyon erişim nesnesi."""

    data: dict = field(default_factory=dict)

    @classmethod
    def load(cls, extra_path: str | None = None) -> "Config":
        user_yaml = _load_yaml(HACKERAGENT_HOME / "config.yaml")
        repo_yaml = _load_yaml(REPO_ROOT / "config.yaml")
        extra_yaml = _load_yaml(Path(extra_path).expanduser()) if extra_path else {}

        merged = _deep_merge(DEFAULTS, repo_yaml)
        merged = _deep_merge(merged, user_yaml)
        merged = _deep_merge(merged, extra_yaml)

        # Environment variable override: OPENROUTER_API_KEY
        env_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if env_key:
            merged.setdefault("llm", {})["openrouter_api_key"] = env_key

        return cls(merged)

    # Kısa erişimciler ─────────────────────────────────────────────────────
    def get(self, path: str, default: Any = None) -> Any:
        """'a.b.c' yolunda nested değer oku."""
        node: Any = self.data
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    @property
    def openrouter_api_key(self) -> str:
        return self.get("llm.openrouter_api_key", "") or ""

    @property
    def base_url(self) -> str:
        return self.get("llm.base_url", "https://openrouter.ai/api/v1")

    @property
    def model_orchestrator(self) -> str:
        return self.get("llm.models.orchestrator", "qwen/qwen3.6-plus")

    @property
    def max_tokens(self) -> int:
        return int(self.get("llm.max_tokens", 4096))

    @property
    def temperature(self) -> float:
        return float(self.get("llm.temperature", 0.3))

    @property
    def timeout_seconds(self) -> int:
        return int(self.get("llm.timeout_seconds", 120))

    @property
    def max_tool_iterations(self) -> int:
        return int(self.get("llm.max_tool_iterations", 25))

    @property
    def mcp_servers(self) -> dict:
        servers = self.get("mcp_servers", {}) or {}
        return {k: v for k, v in servers.items() if v.get("enabled", True)}


# Tek global instance (lazy)
_config: Config | None = None


def get_config(extra_path: str | None = None) -> Config:
    global _config
    if _config is None or extra_path is not None:
        _config = Config.load(extra_path)
    return _config
