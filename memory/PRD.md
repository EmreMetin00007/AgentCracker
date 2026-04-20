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

---

## Faz-B: Akıllı Özellikler (2026-04-20)

### Yeni eklenen 4 özellik
1. 🧠 **Akıllı model router** — `core/router.py` + Orchestrator entegrasyonu
   - Config'de 3 tier: `llm.models.cheap`, `llm.models.orchestrator` (standard), `llm.models.premium`
   - Heuristik seçim: exploit/rapor/PoC → premium; basit sohbet/kısa girdi → cheap; default standard
   - Uzun bağlam (>8000 char) → premium pahalı olmasın diye standard'a düş
   - Her LLM çağrısı öncesi `ModelRouter.pick()` çağrılır, `LLMClient.chat(model=picked)`
   - Flag: `llm.router_enabled: true`

2. 🔄 **MCP auto-restart + circuit breaker** — `core/circuit_breaker.py` + ToolRouter zaten kullanıyordu; Orchestrator'da paylaşılan instance oluşturuldu
   - Per-tool ardışık fail eşiği (default 3) → cooldown (60s) → LLM "circuit open" mesajı alır
   - Per-server toplam fail eşiği (default 5) → `MCPManager.restart_server()` otomatik tetikler
   - CLI: `/circuit` komutu ile canlı stats

3. 📚 **RAG-enhanced context** — `core/rag_context.py` + Orchestrator `ask()` entegrasyonu
   - Her kullanıcı mesajı öncesi `rag-engine.rag_search` + `memory-server.get_target_memory` çağrısı
   - Bulunan kayıtlar system mesajı olarak mesaja eklenir (max 4000 char)
   - Target otomatik tespit ediliyor (IP/domain regex)
   - Flag: `rag.auto_enrich: true`

4. 🪞 **Self-reflection loop** — Orchestrator `ask()` içinde
   - Tool sonucu `HATA:`/`ERROR:` prefix'i ile başlarsa → system mesajı "🔄 REFLECT: ... farklı dene" enjekte edilir
   - Bir sonraki LLM turu `force_cheap_next` ile cheap tier'a yönlendirilir (düzeltme ucuz olsun)
   - Flag: `llm.self_reflection_enabled: true`

### Yeni CLI komutları
- `/circuit` — CircuitBreaker istatistikleri (Rich Table)
- `/models` — Aktif router tier'ları ve model adları

### Testler
- `hackeragent/tests/test_router.py` (11 test)
- `hackeragent/tests/test_circuit_breaker.py` (8 test)
- `hackeragent/tests/test_rag_context.py` (7 test)
- `hackeragent/tests/test_orchestrator_integration.py` (8 test — MCP+LLM mock'lu)
- **33/33 test ✅**

### Test Durumu
- ✅ Unit: 33 test geçti (router heuristics, circuit states, RAG enrichment, orchestrator integration)
- ✅ Lint: `ruff check hackeragent/` temiz
- ✅ Import smoke test: tüm modüller sorunsuz import
- ⚠️ Canlı LLM + MCP E2E test edilmedi (OpenRouter key ve Kali araçları gerektiriyor)

## Backlog / İyileştirmeler
- P2: `rag-engine` için daha hızlı ingest — toplu PayloadsAllTheThings ingest zamanlaması
- P2: REPL'de streaming LLM çıktısı (şu an bloklama var)
- P2: `hackeragent --workflow bug-bounty` komutu ile workflow otomasyonu
- P3: TUI dashboard (Textual tabanlı) — telemetry + active tool calls canlı göster
- P3: Router'da LLM-tabanlı classifier (maliyet analizi yap, ROI varsa devreye al)
- P3: Self-reflection'da ayrı bir "cheap LLM çağrısı + suggestion" yaklaşımı (şu an nudge-only)
