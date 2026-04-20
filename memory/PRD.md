# HackerAgent v3.0 — Claude Code CLI Bağımsızlaştırma

## Orijinal Problem Statement
> "mevcut projeyi claude code cli bagımlılıklarını kaldırmak istiyorum sadece"
> "mevcut projede mcp server koruyarak claude code aradan kaldırmak"

Kullanıcı tercihleri:
- LLM: OpenRouter (Qwen 3.6 Plus + Hermes 4 405B) mevcut yapıyla devam
- API key: Kurulumda `.env` üzerinden verilecek
- Test: Yapısal testler (Kali araç testi yok) + gerektiğinde container'da araç denemesi

## Mimari
Claude Code CLI → Kendi Python orkestratörüne refactor.
MCP mimarisi (kali-tools, memory, ctf-platform, telemetry, rag-engine) korundu.

```
hackeragent CLI (Rich REPL)
   ↓
Orchestrator (OODA Loop, hackeragent/core/orchestrator.py)
   ├── LLMClient (OpenRouter, OpenAI-compatible tool_use)
   ├── MCPManager (stdio, mcp Python SDK client)
   ├── ToolRouter (tool_calls → MCP çağrısı)
   └── PromptEngine (system_prompt.md + rules/ + skills/)
```

## Yapılanlar (2026-04-20)

### Silinenler
- `setup_openrouter.sh` (ANTHROPIC_API_KEY hilesi)
- Node.js/npm/`@anthropic-ai/claude-code` install.sh adımları

### Yeniden Adlandırılanlar
- `CLAUDE.md` → `system_prompt.md`
- `.claude/rules/` → `rules/` (install.sh tarafından runtime oluşturuluyordu; artık repo içinde)

### Yeni Eklenenler
- `hackeragent/` Python paketi
  - `core/config.py` — YAML + .env loader
  - `core/llm_client.py` — OpenRouter client (retry + tool_use)
  - `core/mcp_manager.py` — stdio-based MCP client (sync wrapper)
  - `core/prompt_engine.py` — system prompt birleştirici
  - `core/tool_router.py` — LLM tool_calls → MCP
  - `core/orchestrator.py` — OODA Loop, conversation history
  - `cli/main.py` — argparse + Rich REPL
  - `cli/banner.py`, `utils/logger.py`
- `config.yaml` — merkezi konfigürasyon
- `.env.example` — kullanıcı environment örneği
- `pyproject.toml` + `requirements.txt` — pip paketi
- `rules/scope-guard.md`, `rules/safety-rules.md`

### Değiştirilenler
- Tüm MCP server'larda `~/.claude/` → `~/.hackeragent/` (HACKERAGENT_HOME env var ile override edilebilir, legacy path fallback korundu)
- `FastMCP(description=...)` → `FastMCP(instructions=...)` (MCP SDK 1.27 API değişikliği)
- `scripts/swarm_orchestrator.py` — Claude modelleri → Qwen
- `install.sh` tamamen yeniden yazıldı (Node.js/CLI kaldırıldı, `pip install -e .` eklendi, `.env` kurulumu eklendi)
- `README.md` — v3.0 mimarisi yansıtıldı
- `workflows/*.md` — "Claude Code" → "HackerAgent orkestratörü"

## Test Durumu (Yapısal — a seçeneği)
- ✅ `hackeragent` + `hackeragent --version` + `hackeragent --help` çalışıyor
- ✅ `hackeragent --list-tools` → **5 MCP server aktif, 112 tool yüklü**
- ✅ Gerçek MCP tool çağrısı: `telemetry.get_metrics_dashboard` → 430 char response
- ✅ Standalone scriptler: `attack_planner.py`, `recon_daemon.py`, `swarm_orchestrator.py --help`
- ✅ `ruff` temiz (sadece preexisting f-string uyarısı)
- ✅ MCP stdout protokol handshake temiz (JSON-RPC only)
- ⚠️ **Canlı LLM çağrısı test edilmedi** — gerçek OpenRouter API key ile kullanıcı kendi ortamında doğrulamalı.

## Geriye Uyumluluk
- Eski `~/.claude/settings.json` hâlâ OpenRouter key'i için okunuyor (fallback)
- Eski `~/.claude/agent_memory.db` vs. okunmuyor; kullanıcı `HACKERAGENT_HOME=~/.claude` ile zorlanabilir ya da elle taşıyabilir.

## Next Action Items (kullanıcıdan bekleniyor)
1. Gerçek `OPENROUTER_API_KEY` ile `.env` oluşturup `hackeragent` çalıştırma.
2. Eski `~/.claude/` verileri varsa `~/.hackeragent/` altına taşıma (opsiyonel).
3. Opsiyonel: `git commit` + push.

## Backlog / İyileştirmeler
- P2: `rag-engine` için daha hızlı ingest — toplu PayloadsAllTheThings ingest zamanlaması
- P2: REPL'de streaming LLM çıktısı (şu an bloklama var)
- P2: `hackeragent --workflow bug-bounty` komutu ile workflow otomasyonu
- P3: TUI dashboard (Textual tabanlı) — telemetry + active tool calls canlı göster
