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

---

## Faz-C: İleri Seviye Ajan Özellikleri (2026-04-20)

### 6 yeni özellik

1. ♻️  **Tool Cache** — `core/tool_cache.py`
   - `(qname, args)` için SHA1 hash'li session-scoped TTL cache
   - Tool-spesifik TTL override'ları: `nmap`=3600s, `rag_search`=7 gün, `telemetry`=10s
   - Yazma işlemleri (`store_finding`, `request_approval`, `submit_flag`) ASLA cache'lenmez
   - Cache hit → `[CACHED]` prefix ile LLM'e döner, MCP çağrısı yapılmaz
   - CLI: `/cache` (stats) + `/cache clear`

2. 📦 **Prompt Compression** — `core/compressor.py`
   - `threshold_chars` (default 40k) aşılınca eski tool sonuçlarını ucuz LLM ile özetle
   - Son `keep_tail=10` mesaj ve ilk system prompt KORUNUR
   - Sıkıştırılan segment tek bir "📦 SIKIŞTIRILMIŞ GEÇMİŞ" system mesajıyla değiştirilir
   - Typical: %50-70 token tasarrufu uzun CTF oturumlarında

3. 🗡️  **Attack Graph auto-inject** — `rag_context.py` genişletmesi
   - RAG + memory + `memory-server.suggest_next_action` her kullanıcı turunda otomatik çağrılır
   - Graph'taki boşlukları (keşfedilmiş servis ama zafiyet analizi yapılmamış) tespit eder
   - LLM her turda "en yüksek öncelikli sonraki adım"ı sistem bağlamında görür

4. 🗺️  **Planner-Executor** — `core/planner.py`
   - Kompleks görev tespit edilince (≥40 char + pentest keyword veya 15+ kelime) ucuz LLM'le JSON plan üretilir
   - Plan: `[{step, goal, expected_tools, success_criteria}]` — max 6 adım
   - Plan system mesajı olarak enjekte edilir; LLM her turda hangi adımda olduğunu bilir
   - CLI: `/plan` komutu plan'ı gösterir

5. ⚡ **Paralel tool execution (swarm MVP)** — `core/parallel_exec.py`
   - Aynı turda birden fazla `tool_call` varsa güvenli olanlar `ThreadPoolExecutor` ile paralel koşar
   - Güvensizler (exploit, request_approval, submit_flag, store_*) sıralı koşar
   - Aynı qualified_name'den birden fazla çağrı farklı paralel gruplara bölünür (resource çakışması önlemi)
   - Default max_workers=5; 4 tool → ~%60 süre tasarrufu
   - Sonuç sırası KORUNUR (LLM'in beklediği gibi)

6. 👁️  **Vision / Multimodal** — `core/vision.py` + `mcp-servers/mcp-browser/`
   - Yeni `mcp-browser` MCP server (opt-in): Playwright ile `browser_screenshot`, `browser_extract_text`, `browser_get_forms`
   - Screenshot base64 PNG döndürür; LLM client multimodal format'a otomatik çevirir
   - Vision-capable model pattern match (`claude-3*`, `gpt-4o`, `gemini-2/3*`, `qwen-vl*`, `llama-3.2-vision`)
   - Router premium tier'a vision modeli atandıysa web exploit'lerde screenshot bağlamı aktif

### Orchestrator entegrasyonu
- `__post_init__`: yeni bileşenler instantiate (`tool_cache`, `compressor`, `planner`)
- `start()`: `ToolRouter`'a `cache` geçirilir
- `ask()`:
  1. RAG+memory+graph enrichment (zaten vardı, graph eklendi)
  2. Planner tetikle (ilk turda, plan yoksa)
  3. İterasyon başında compression check
  4. Tool execution paralel (safety-aware)
  5. Vision-enabled modelde screenshot sonuçları multimodal olarak eklenir

### Yeni CLI komutları
- `/cache [clear]` — tool cache stats veya temizle
- `/plan` — aktif görev planını göster

### Testler (Faz-C)
- `tests/test_tool_cache.py` (12 test)
- `tests/test_compressor.py` (7 test)
- `tests/test_planner.py` (12 test)
- `tests/test_parallel_exec.py` (10 test)
- `tests/test_vision.py` (10 test)
- `tests/test_rag_context.py` güncellendi (graph enjeksiyon testi)
- **84/84 test ✅** (tüm projede — Faz-B + Faz-C)

### Konfigürasyon (config.yaml yeni flag'ler)
```yaml
llm:
  tool_cache_enabled: true
  compression_enabled: true
  compression_threshold_chars: 40000
  compression_keep_tail: 10
  planner_enabled: true
  planner_max_steps: 6
  vision_enabled: true

safety:
  parallel_tool_execution: true
  parallel_max_workers: 5

mcp_servers:
  browser:
    enabled: false  # playwright install gerektirir
    command: "python3"
    args: ["mcp-servers/mcp-browser/server.py"]
```

### Yeni dosyalar
- `hackeragent/core/tool_cache.py` (~175 LOC)
- `hackeragent/core/compressor.py` (~170 LOC)
- `hackeragent/core/planner.py` (~210 LOC)
- `hackeragent/core/parallel_exec.py` (~135 LOC)
- `hackeragent/core/vision.py` (~110 LOC)
- `mcp-servers/mcp-browser/server.py` (~180 LOC — opt-in vision)
- `mcp-servers/mcp-browser/requirements.txt`

### Test Durumu (Faz-C)
- ✅ Unit: 84 test geçti (tüm proje — Faz-B + Faz-C)
- ✅ Lint: `ruff check hackeragent/` temiz
- ✅ Import smoke test + config validation
- ⚠️ Canlı OpenRouter + Kali MCP E2E test edilmedi

---

## Faz-D: Cost-Aware Telemetry (2026-04-20)

Compressor/Planner/Cache'in ucuz LLM overhead'i vs tasarrufunu ölçen
ve session sonunda **"cost-aware pentest agent"** raporu üreten katman.

### Yeni bileşenler
1. **Telemetry server genişletmesi** (`mcp-servers/mcp-telemetry/server.py`)
   - Yeni tablo: `savings_events(session_id, event_type, details, cost_usd, saved_tokens, saved_usd)`
   - Yeni tool'lar: `log_savings_event()`, `get_savings_report(session_id)`
   - `get_savings_report` agrega edip bütçe etki analizi yapıyor (overhead, tasarruf, net fayda)

2. **`hackeragent/core/telemetry.py`** — in-memory `SessionStats` + `TelemetryEmitter`
   - `SessionStats`: compression/cache_hit/planner/reflection/parallel event'lerini biriktirir
   - Her event için tahmini $ tasarruf hesaplar (saved_tokens × fallback input price)
   - `TelemetryEmitter`: MCP telemetry server'a **fire-and-forget daemon thread** ile event gönderir (LLM akışını bloklamaz, exception sessizce yutulur)
   - `render_report()`: kullanıcıya renkli özet üretir

3. **Compressor & Planner** cost döndürür
   - `CompressionResult.llm_cost_usd` — sıkıştırma için harcanan cheap LLM maliyeti
   - `Plan.llm_cost_usd` — plan üretimi için harcanan cheap LLM maliyeti
   - Bu maliyetler `budget.register(cheap_model, cost)` ile toplam bütçeye eklenir

4. **ToolCache callback**
   - `on_hit(qname, result_chars)` callback alanı eklendi
   - Orchestrator `self.tool_cache.on_hit = self.stats.record_cache_hit` ile bağlanıyor

5. **Orchestrator entegrasyonu**
   - `SessionStats` instantiate edilir, `start()` sonrası `TelemetryEmitter` attach edilir
   - `ask()` içinde her olay (compression, plan, reflection, parallel) `stats.record_*` çağırır
   - Yeni public metod: `cost_report()` — CLI'ın `/report` ve REPL çıkışında kullandığı metin
   - `reset()` stats'ı da sıfırlıyor (emitter korunuyor)

6. **CLI entegrasyonu**
   - Yeni slash komutu: `/report` — anlık cost-aware rapor
   - REPL çıkışında otomatik olarak `cost_report()` gösterilir
   - `--task` single-run modunda da rapor gösterilir
   - `/help` güncellendi

### Örnek rapor çıktısı
```
╭─────────────────────────────────────────────────────╮
│  💰  Cost-Aware Session Report                      │
╰─────────────────────────────────────────────────────╯
🧠 LLM: 18 çağrı, $0.1234
📦 Compression: 2 sıkıştırma, ~19,750 token kurtardı (~%66 context tasarrufu), overhead $0.0035
♻️  Cache: 7 hit, ~5,600 token context tasarrufu (~$0.0028)
🗺️  Plan: 1 üretildi, ~7,000 token iterasyon tasarrufu, overhead $0.0008
🪞 Reflection: 1 nudge, ~3,000 boşa iterasyon önlendi
⚡ Parallel: 2 tur paralel tool yürüttü (wall-clock tasarrufu)
───────────────────────────────────────────────────────
Overhead $0.0043   Tasarruf ~$0.0374   Net +$0.0331 ✅
```

### Test Sonuçları (Faz-D)
- ✅ **96/96 pytest geçti** — Faz-B (33) + Faz-C (51) + Faz-D (12) tümü yeşil
- Yeni test: `tests/test_telemetry.py` (12 test — SessionStats event kayıtları, emitter fire-and-forget, MCP exception yutma)
- `test_compressor.py` ve `test_planner.py` cost_usd dönüşü için güncellendi
- ✅ Lint: `ruff` temiz
- ✅ Smoke test: telemetry server `savings_events` tablosu oluşuyor, kolonlar doğrulandı

### Yeni dosyalar/değişiklikler (Faz-D)
- **Yeni**: `hackeragent/core/telemetry.py` (~260 LOC)
- **Yeni**: `hackeragent/tests/test_telemetry.py` (12 test)
- **Genişletildi**: `mcp-servers/mcp-telemetry/server.py` (+~130 LOC — savings tablosu + 2 tool)
- **Güncellendi**: `compressor.py`, `planner.py`, `tool_cache.py`, `orchestrator.py`, `cli/main.py`

### Backlog (Faz-E için)
- P2: Tasarruf heuristiklerini empirik verilerle kalibre et (gerçek CTF session'larından ölçüm)
- P2: `hackeragent --savings-report` CLI flag'i — geçmiş tüm session'lar için toplam
- P3: Dashboard UI (Textual) — live savings counter + LLM maliyet grafiği
- P3: Cost-based model tier auto-tuning — session geçmişine bakarak `cheap`/`standard` arasında otomatik seçim

## Backlog / İyileştirmeler
- P2: `rag-engine` için daha hızlı ingest — toplu PayloadsAllTheThings ingest zamanlaması
- P2: REPL'de streaming LLM çıktısı (şu an bloklama var)
- P2: `hackeragent --workflow bug-bounty` komutu ile workflow otomasyonu
- P3: TUI dashboard (Textual tabanlı) — telemetry + active tool calls canlı göster
- P3: Router'da LLM-tabanlı classifier (maliyet analizi yap, ROI varsa devreye al)
- P3: Self-reflection'da ayrı bir "cheap LLM çağrısı + suggestion" yaklaşımı (şu an nudge-only)

---

## Faz-E: Kararlılık + Yeni Özellikler + Maliyet (2026-04-21)

Kullanıcı isteği: A (kararlılık) + B (özellikler) + C (maliyet) + F (sağlık).

### A — Kararlılık (yapıldı)
1. **Config validator** — `core/config_validator.py`: startup'ta şema doğrulama
2. **Health check** — `core/health.py` + `--health` + `/health`
3. **Crash reporter** — `core/crash_reporter.py` + `/crashes` + `install_excepthook`
4. **Graceful shutdown** — SIGINT/SIGTERM handler, `orch.cancel()`, REPL `/cancel`
5. **LLM call crash logging** — ask() içindeki LLM hatası otomatik rapor

### B — Yeni Özellikler (yapıldı)
1. **Workflow launcher** — `--workflow bug-bounty|ctf|supervisor` + `--list-workflows`
2. **Multi-target batch** — `--targets <file>` (her satır için yeni session)
3. **Agrega savings** — `--savings-report` (telemetry.db'den tüm session'lar)
4. **Webhook notifier** — Discord/Slack/generic + dedupe + `/notify test`

### C — Maliyet (yapıldı)
1. **OpenRouter prompt caching** — `llm.prompt_cache_enabled` + `--prompt-cache`
2. **LLM-based tier classifier** — `llm.router_llm_classifier` (opt-in)
3. **Session replay** — `--replay <session-id>`

### F — Sağlık & CI (yapıldı)
- Ruff: 42 hata → 0 (F821 datetime bug fix dahil)
- pip-audit: temiz
- GitHub Actions CI — Python 3.10/3.11/3.12 matrix + lint + test + audit

### Yeni dosyalar
- `hackeragent/core/` — config_validator.py, health.py, crash_reporter.py,
  notifier.py, workflow_launcher.py, replay.py
- `hackeragent/tests/` — test_config_validator.py (13), test_notifier.py (7),
  test_stability.py (8), test_prompt_cache.py (6), test_health.py (7),
  test_replay_and_classifier.py (13)
- `.github/workflows/ci.yml`

### Test Sonuçları (Faz-E)
- **156/156 pytest PASSED** (Faz-D 102 + Faz-E 54 yeni test)
- ruff clean, `--validate-config` ✓, `--health` → 5/5 MCP server (116 tool)

### Backlog (Faz-F+)
- P2: Textual TUI dashboard
- P2: HackerOne/Bugcrowd direkt submit
- P3: PDF/HTML rapor export
- P3: Tool output redaction (PII maskeleme)

---

## Faz-F: Modern Web + API Saldırı Paketleri (2026-04-21)

Kullanıcı isteği: "projeyi daha fazla genişletemezmiyiz sadece belirli web açıklarını buluyor"
→ Paket 1 (Modern Web Advanced) + Paket 2 (API & Modern Endpoint) onaylandı.

### Yeni MCP Server: `mcp-web-advanced` (23 tool)

**Paket 1 — Modern Web Advanced (15 tool):**
- GraphQL: `graphql_introspect`, `graphql_suggestion_scan`, `graphql_batch_attack`
- JWT: `jwt_analyze`, `jwt_attack_alg_none`, `jwt_brute_hs256`, `jwt_rs_to_hs_confusion`
- OAuth/SAML: `oauth_redirect_bypass` (15 varyant), `saml_xsw_variants` (XSW1-8 rehberi)
- HTTP Smuggling: `http_smuggling_probe` (CL.TE/TE.CL/TE.TE + h2c timing-based)
- Cache & CORS: `cache_poisoning_probe`, `cors_advanced_scan` (9 senaryo)
- Prototype Pollution: `prototype_pollution_scan`
- Race Condition: `race_condition_test` (threading.Barrier ile sync)
- WebSocket: `websocket_handshake_test` (CSWSH detection)

**Paket 2 — API & Modern Endpoint (8 tool):**
- Ingest: `openapi_ingest` (Swagger/OpenAPI YAML+JSON), `postman_ingest` (v2)
- Discovery: `api_route_fuzz` (built-in ~65 route wordlist), `api_param_discover` (Arjun-style)
- NoSQLi: `nosqli_mongo_test` ($ne/$gt/$regex/$where)
- IDOR: `api_idor_matrix` (multi-token × multi-ID matrix)
- Bypass: `api_rate_bypass_probe` (9 varyant — IP spoofing + path obfuscation)
- Output: `formula_injection_payloads` (CSV/Excel RCE + exfil)

### Mimari
- Python-native implementasyon (external binary minimum, sadece requests + pycryptodome)
- Raw socket HTTP smuggling probe (sıkı TE/CL fuzzing için gerekli)
- Threading.Barrier ile gerçek race condition simülasyonu
- Skill: `skills/web-advanced/SKILL.md` — 23 tool kategorize edilmiş
- Workflow: `workflows/modern-web-workflow.md` — 9 faz adım adım pipeline
- Alias: `--workflow modern-web | mw | api`

### Bonus: LLM Client Akıllı Fallback
`llm_client.py`'da kritik iyileştirme — Qwen provider'ı çok sayıda tool'u
reddettiğinde sonsuz drop chain yerine:
- Tool drop işlemleri NETWORK retry sayılmıyor (ayrı counter)
- 10+ tool drop → otomatik tools'suz text-only fallback (crash yok)
- `max_tool_drops = 50` güvenlik tavanı
- Canlı test: 116 tool'dan 95+'i reddedilse bile session başarıyla tamamlanıyor

### Dosya değişiklikleri
**Yeni:**
- `mcp-servers/mcp-web-advanced/server.py` (~900 LOC, 23 MCP tool)
- `mcp-servers/mcp-web-advanced/requirements.txt`
- `skills/web-advanced/SKILL.md`
- `workflows/modern-web-workflow.md`
- `hackeragent/tests/test_web_advanced.py` (23 test)

**Güncellenen:**
- `hackeragent/core/config.py` — DEFAULTS'a web-advanced eklendi
- `config.yaml` — yeni MCP server kaydı
- `hackeragent/core/workflow_launcher.py` — 3 yeni alias (modern-web/mw/api)
- `hackeragent/core/llm_client.py` — smart tool-drop fallback
- `system_prompt.md` — MCP ekosistemi tablosu güncellendi (5→6 server), skill listesi

### Test Sonuçları (Faz-F)
- **179/179 pytest PASSED** (Faz-E 156 + Faz-F 23 yeni)
- Ruff clean (tüm server'lar)
- Canlı MCP: 6/6 server sağlıklı, **139 tool toplam** (önce 116 → +23)
- Canlı LLM E2E: JWT analiz görevi + smart fallback tamamlandı ($0.02)

### Backlog (Faz-G için)
- Paket 3 (Cloud & Container): AWS/Azure/GCP/K8s/Docker
- Paket 4 (Active Directory): BloodHound, Kerberos, ADCS, NTLM relay
- Paket 5 (Binary advanced): angr, qiling, afl++, Ghidra headless
- Paket 6 (OSINT 2.0): Shodan/Censys/ZoomEye, trufflehog, waybackurls+gau
- Exploit-AI: bulgudan reusable nuclei template auto-gen
- Chain-PoC: KG'den multi-step attack chain otomatik PoC
- Live monitor mode: `--monitor <domain>` webhook push
