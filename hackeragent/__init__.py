"""HackerAgent v3.0 — Otonom pentest / CTF / bug-bounty orkestratörü.

Claude Code CLI'dan bağımsız; OpenRouter (Qwen + Hermes) üzerinde çalışır.
MCP server'ları (kali-tools, memory, ctf-platform, telemetry, rag-engine) stdio
üzerinden yönetir ve LLM'in tool-use API'si ile araçları çağırır.
"""

__version__ = "3.0.0"
__all__ = ["__version__"]
