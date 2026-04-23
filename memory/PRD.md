# CCO — Claude Code Offensive Operator

## Original Problem Statement
AgentCracker v3.1'in (4.327 satır Python orkestrasyon kodu ile) Claude Code CLI +
OpenRouter mimarisine migrasyonu. Hedef: silinen 4.300+ satır Python kod, korunan
6 MCP server (139+ tool), 7 skill, 4 workflow, 2 rules; eklenen `CLAUDE.md`, `.env`,
`~/.claude.json`, `install-cco.sh`. Platform: Kali Linux CLI. LLM: OpenRouter
(`ANTHROPIC_BASE_URL` override ile Qwen 3 / Hermes 4 / Llama 3.3).

## Architecture
- **Orkestratör:** Claude Code CLI v2.1.118 (npm global)
- **LLM transport:** `ANTHROPIC_BASE_URL=https://openrouter.ai/api` + `ANTHROPIC_AUTH_TOKEN`
- **Session modeli:** `qwen/qwen3-next-80b-a3b-instruct` (non-thinking, tool use uyumlu,
  alias `sonnet`). Thinking-only modeller (`qwen/qwen3.6-plus`) session modeli olarak
  çalışmaz (boş result döndürür); sadece MCP tool içinden programatik çağrıda kullanılır.
- **6 MCP server** stdio transport ile subprocess olarak başlatılır
- **Model delegation:** CLAUDE.md'de kurallar yazılı; Claude Code doğru tool'u seçer,
  tool'lar `os.environ.get("CCO_ANALYZE_MODEL", ...)` ile OpenRouter'a istek atar
- **Veri:** `~/.cco/` altında SQLite (memory), ChromaDB (rag), logs, approvals

## User Personas
- **Pentester / Bug bounty hunter:** `source .env && claude` → Recon'dan rapora
  uzanan otonom saldırı zinciri
- **CTF solver:** Web/Pwn/Crypto/Forensics challenge'ları Kali araçları + LLM
  analizi ile çözer
- **Security researcher:** Hermes 405B ile özel PoC üretimi, sansürsüz analiz

## Core Requirements (Static)
1. Python orkestrasyon kodunun tamamı silinmeli (PRD §9)
2. MCP server'lar Claude Code tarafından keşfedilebilir ve çağrılabilir olmalı
3. OpenRouter üzerinden çalışan modeller session modeli olarak tool use desteklemeli
4. Model routing MCP tool içinde yapılmalı (session içinde model değişmez)
5. CLAUDE.md @reference syntax ile skills/workflows/rules lazy-load etmeli
6. `install-cco.sh` tek komutla Kali'de kurulumu tamamlamalı
7. Scope enforcement + budget tracking (telemetry MCP) aktif olmalı

## What's Been Implemented

### 2026-01-23 — Migration MVP (Faz 0 → 3 tümü tek oturumda)
- **Faz 0 — Test & Temizlik** (✅ TAMAMLANDI)
  - Claude Code CLI v2.1.118 npm ile kuruldu
  - OpenRouter Text + Tool use uyum testi: `qwen/qwen3-next-80b-a3b-instruct`,
    `meta-llama/llama-3.3-70b-instruct` session modeli olarak çalışıyor
  - `qwen/qwen3.6-plus` thinking-only → sadece MCP tool içinde kullanılacak
  - **4.327 satır Python silindi:** `hackeragent/`, `pyproject.toml`,
    `requirements.txt`, `config.yaml`, `.github/`, `memory/`, `install.sh`, `.emergent/`

- **Faz 1 — MCP Entegrasyonu** (✅ TAMAMLANDI)
  - Tüm MCP server'larda `HACKERAGENT_HOME` → `CCO_HOME` rename
  - `~/.hackeragent` default → `~/.cco` değişti
  - `keyring.get_password("hackeragent")` → `keyring.get_password("cco")`
  - HTTP-Referer `hackeragent.local` → `cco.local`
  - `qwen_analyze`, `generate_exploit_poc`, `parallel_llm_analyze` tool'ları
    hardcoded model yerine `CCO_ANALYZE_MODEL` / `CCO_EXPLOIT_MODEL` env okuyor
  - `get_api_key_secure()` hem `OPENROUTER_API_KEY` hem `ANTHROPIC_AUTH_TOKEN` okuyor
  - Python bağımlılıkları: `mcp[cli]`, `chromadb`, `networkx`, `pycryptodome`,
    `PyYAML`, `beautifulsoup4`, `dnspython`, `aiohttp`, `requests` (+fastmcp)
  - 6 MCP server import testi ✅ (kali-tools, memory-server, telemetry, rag-engine,
    ctf-platform, web-advanced)
  - `ruff check mcp-servers/` — All checks passed

- **Faz 2 — CLAUDE.md + Config** (✅ TAMAMLANDI)
  - `CLAUDE.md` yazıldı (12.6KB): CCO header + MCP tool ekosistemi +
    model delegation kuralları + OODA + Kill Chain + CTF metodoloji +
    Phase 7 (OOB/browser/JS) + `@rules/` `@skills/` `@workflows/` lazy-load
  - `.env` (gerçek key ile) + `.env.example`
  - `install-cco.sh` (13.2KB, 7 faz: Kali araçları → Python deps → veri dizini
    → Claude Code → .env setup → ~/.claude.json MCP kayıt → doğrulama)
  - `~/.claude.json` — 6 MCP server CCO_HOME env ile kayıtlı
  - `README.md` v2.0 için yeniden yazıldı
  - `.gitignore` CCO için güncellendi (.env, ~/.cco, .claude.json* hariç tutuldu)
  - `scripts/budget-check.sh` (OpenRouter credits)
  - `scripts/model-list.sh` (filtreli model listesi)

- **Faz 3 — E2E Doğrulama** (✅ TAMAMLANDI, container'da)
  - ✅ `claude -p "Which MCP servers..."` → 6 server listeleyor: ctf-platform,
    kali-tools, memory-server, rag-engine, telemetry, web-advanced
  - ✅ `store_finding(target='test-target.lab', vulnerability_type='SQL Injection',
    severity='critical', details='...')` → `~/.cco/agent_memory.db` SQLite'a
    yazıldı, Knowledge Graph'te node+edge oluştu
  - ✅ `qwen_analyze(target='192.168.1.1', data='Port 22 OpenSSH 7.4, Port 80
    Apache 2.4.49', analysis_type='vulnerability')` → OpenRouter'a
    `qwen/qwen3.6-plus` ile istek gitti, **CVE-2021-41773 doğru tespit edildi**
  - ✅ `ruff check` — All checks passed

## Architecture Decisions

### OpenRouter Claude Code compat (Jan 2026)
- `ANTHROPIC_API_KEY` yerine `ANTHROPIC_AUTH_TOKEN` kullan (aksi halde OAuth denenir)
- Base URL `/api` (NOT `/api/v1`) — Claude Code kendisi `/v1/messages` ekler
- `ANTHROPIC_DEFAULT_HAIKU_MODEL/SONNET/OPUS` env ile alias mapping yap,
  çünkü Claude Code varsayılan olarak Anthropic model listesini validate eder
- Thinking-only modeller session modeli değil — `qwen/qwen3.6-plus` sadece
  MCP tool içinden `requests.post` ile çağrılır

### Container compatibility
- Root/sudo container için `IS_SANDBOX=1` env gerekli (Claude Code v2.x)
- `--dangerously-skip-permissions` yerine `--permission-mode bypassPermissions`
  non-interactive modda daha güvenli

## Backlog (P0 / P1 / P2)

### P0 (must-have before real-world use)
- [ ] Her skill dosyasının Claude Code tarafından `@skills/...` ile okunabildiğini
      (lazy-load) gerçek bir bug bounty senaryosunda doğrula
- [ ] `scope-guard.md` ve `safety-rules.md` işletme davranışını (`/scope add`
      REPL komutu yerine doğal dil "scope: 10.10.10.0/24" ile) gerçek test et

### P1 (nice-to-have)
- [ ] `mcp-browser` server'ını install-cco.sh'da default olarak kayıt et
      (playwright yüklüyse)
- [ ] `telemetry` MCP server'ına OpenRouter `usage.cost` alanını otomatik çekme
- [ ] `rag-engine` ilk çalıştırmasında Exploit-DB/CVE feed'ini bootstrap et
- [ ] TryHackMe/HTB session resume (Claude Code'un kendi `--resume` session'ı
      ile entegrasyon test)

### P2 (future)
- [ ] `bug-bounty-workflow.md` için custom slash command `/bugbounty <target>`
- [ ] Web UI (Claude Code for VSCode ile entegrasyon)
- [ ] Docker image (pre-built Kali + CCO)

## Test Credentials
Bu proje kullanıcı authentication içermez — OpenRouter API key'i tek credential.
Key `.env` dosyasında, chmod 600 ile korumalı. Detay: `/app/memory/test_credentials.md`.

## Risks & Mitigations

| Risk | Durum | Önlem |
|------|-------|-------|
| OpenRouter Claude Code tool use compat | ✅ Doğrulandı (qwen3-next-80b-a3b-instruct) | Faz 0'da test edildi |
| MCP server'lar `hackeragent` import alır | ✅ Yok | `grep` ile doğrulandı, 0 import |
| CLAUDE.md büyük (12.6KB) | ✅ Kabul edilebilir | Skills/workflows @reference ile lazy-load |
| Hermes 405B session modeli olarak | ✅ Önlendi | Sadece `generate_exploit_poc` tool içinden |
| Thinking model session'da boş result | ✅ Önlendi | `ANTHROPIC_DEFAULT_SONNET_MODEL=qwen3-next-80b-a3b-instruct` (non-thinking) |
| Root container'da permission reddi | ✅ Önlendi | `.env` içinde `IS_SANDBOX=1` |

## Next Actions
1. Kullanıcı Kali ortamında `./install-cco.sh` çalıştırsın; gerçek tools
   (nmap, sqlmap vs.) container'da eksik olabilir, Kali'de tam çalışır
2. TryHackMe / HackTheBox Easy makine ile Faz 3 real-usage test
3. `telemetry` ile session maliyet dashboard'unu kullan
4. CLAUDE.md'yi ilk deneyime göre güncelle
