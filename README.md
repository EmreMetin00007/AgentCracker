# 🔴 HackerAgent v3.1

**Otonom Bug Bounty Avcısı & CTF Çözücü — Claude Code CLI'dan Bağımsız**

HackerAgent, OpenRouter (Qwen 3.6 Plus + Hermes 405B) üzerinde çalışan kendi
orkestratörüne sahip bağımsız bir güvenlik platformudur. MCP (Model Context
Protocol) mimarisini koruyarak Kali Linux güvenlik araçlarına, knowledge
graph hafızasına, RAG bilgi tabanına ve telemetriye tek bir CLI üzerinden
erişir. Kill Chain metodolojisi, OODA Loop karar döngüsü ve 200+ zafiyet tipi
ile donatılmıştır.

> **v3.0 → v3.1 değişikliği:** Faz-E yenilikleri eklendi:
> - ✅ **Kararlılık**: config validator, health check, crash reporter, graceful shutdown
> - ✅ **Yeni özellikler**: `--workflow`, `--targets` (batch), `--savings-report`, webhook notifier
> - ✅ **Maliyet**: OpenRouter prompt caching, LLM-based tier classifier, session replay
> - ✅ **CI**: GitHub Actions — lint + test + audit
> - 156 unit test (+%53), tüm ruff uyarıları temiz

## ⚡ Tek Komutla Kurulum

```bash
# 1. Kali Linux'ta repoyu klonla
git clone https://github.com/KULLANICI/HackerAgent.git
cd HackerAgent

# 2. Kurulum scriptini çalıştır
chmod +x install.sh
sudo ./install.sh
# (Kurulum sırasında OpenRouter API key'iniz sorulacak)

# 3. Orkestratörü başlat
hackeragent
```

`install.sh` şunları yapar:
- ✅ Kali güvenlik araçlarını kurar (nmap, sqlmap, ffuf, nuclei, hashcat, john, gdb, binwalk, ...)
- ✅ Python bağımlılıklarını ve `hackeragent` paketini kurar (`pip install -e .`)
- ✅ Wordlist'leri hazırlar (rockyou.txt, seclists)
- ✅ `~/.hackeragent/` veri dizinini oluşturur (DB, RAG, loglar, approvals)
- ✅ OpenRouter API key'i `.env` dosyasına kaydeder
- ✅ GDB eklentilerini (GEF) ve Ruby gem'lerini kurar

---

## 🏗️ Mimari

```
┌─────────────────────────────────────────────┐
│   hackeragent CLI (Rich tabanlı REPL)       │
│   Kullanıcı: "example.com'u tara"           │
└───────────────────┬─────────────────────────┘
                    │
        ┌───────────▼────────────┐
        │   Orchestrator (OODA)  │  ← system_prompt.md + rules/ + skills/
        └───┬────────────────┬───┘
            │                │
 ┌──────────▼──┐      ┌──────▼──────────┐
 │ LLMClient   │      │ MCPManager      │
 │ OpenRouter  │      │ (stdio sürücü)  │
 │ Qwen/Hermes │      └──────┬──────────┘
 └─────────────┘             │
                   ┌─────────┼─────────┬────────────┬──────────┐
                   │         │         │            │          │
              kali-tools  memory  ctf-platform  telemetry  rag-engine
              (MCP)       server   (MCP)        (MCP)      (MCP)
```

### 🧠 Hacker Persona (`system_prompt.md`)
- **Kill Chain** metodolojisi (Recon → Exploit → Post-Exploit → Report)
- **OODA Loop** karar döngüsü
- Tüm güvenlik disiplinleri için detaylı prosedürler

### ⚡ 6 Güvenlik Skill'i

| Skill | Kapsam |
|-------|--------|
| `recon-enumeration` | Nmap, subdomain, OSINT, port scan, DNS, dizin keşfi |
| `web-exploit` | SQLi, XSS, SSRF, SSTI, LFI, CMDi, file upload, deserialization |
| `binary-pwn` | Buffer overflow, ROP, format string, heap, pwntools, GDB |
| `crypto-forensics` | RSA/AES saldırıları, hash cracking, steganografi, Volatility, PCAP |
| `ctf-solver` | Ana orkestratör — kategori tanımlama, iteratif çözüm |
| `report-generator` | HackerOne rapor formatı, CVSS hesaplama, düzeltme önerileri |

### ⚙️ 5 MCP Server

| Server | Araçlar |
|--------|---------|
| `kali-tools` | 40+ araç: nmap, ffuf, sqlmap, nikto, nuclei, hydra, hashcat, john, volatility, qwen_analyze, generate_exploit_poc, ... |
| `ctf-platform` | CTFd, HackTheBox, TryHackMe API + decode/hash yardımcıları |
| `memory-server` | NetworkX Knowledge Graph + SQLite (attack path planning) |
| `telemetry` | Tool/LLM call tracking, maliyet dashboard'u |
| `rag-engine` | ChromaDB ile CVE/exploit/writeup semantic search |

### 🧬 Hibrit LLM Mimarisi

| Model | Rol | Nasıl Tetiklenir |
|-------|-----|------------------|
| **Qwen 3.6 Plus** | Orkestratör + analiz | Her zaman aktif (default) |
| **Hermes 4 405B** | PoC exploit üretici | `generate_exploit_poc`, `parallel_llm_analyze` |

---

## 🎯 Kullanım Örnekleri

```bash
# Sağlık kontrolü & validation
hackeragent --validate-config    # config.yaml şemasını doğrula
hackeragent --health             # 5 MCP server health-check
hackeragent --list-workflows     # bug-bounty / ctf / supervisor

# Workflow launcher — hazır metodoloji ile başlat
hackeragent --workflow bug-bounty --task "example.com için bounty avı"
hackeragent --workflow ctf --task "picoCTF Binary Exploitation"

# Batch multi-target mode
hackeragent --targets targets.txt --task "Her hedef için full recon"

# Agrega savings raporu (tüm sessionların toplamı)
hackeragent --savings-report

# Maliyet optimizasyonu
hackeragent --prompt-cache       # OpenRouter ephemeral cache (~%50 input tasarruf)
hackeragent --replay <session-id> # Eski session'u yeni promptlarla regression test
```

```bash
# İnteraktif REPL (streaming varsayılan aktif)
hackeragent

# REPL içinde:
> 10.10.10.10 hedefini tara ve zafiyetleri bul
> example.com üzerinde kapsamlı güvenlik testi yap
> Bu binary dosyasını analiz et ve exploit yaz
> Bulduğum SQL injection için HackerOne raporu yaz

# REPL slash komutları:
/tools                 # Aktif MCP araçlarını listele
/sessions              # Geçmiş session'ları göster
/budget                # Mevcut maliyet özeti
/scope list            # Aktif scope'u göster
/scope add 10.10.10.5  # Scope'a host/IP/CIDR ekle
/scope rm example.com  # Scope'tan kaldır
/scope clear           # Scope'u sıfırla
/cache                 # Tool cache istatistikleri
/cache clear           # Tool cache'i temizle
/plan                  # Aktif görev planını göster
/report                # 💰 Cost-aware session raporu
/health                # 🏥 MCP server health-check
/crashes               # Son crash raporlarını göster
/notify test           # Webhook notifier test bildirimi
/cancel                # Mevcut görev turunu iptal et
/help                  # Tüm komutlar
/exit                  # Çık
```

```bash
# Tek görev (REPL açmadan, streaming ile)
hackeragent --task "10.10.10.10 portlarını tara" --scope 10.10.10.0/24

# Bütçe limiti — $5 aşılırsa session durur
hackeragent --budget 5.00

# Streaming kapat (yavaş terminal için)
hackeragent --no-stream

# Session resume
hackeragent --resume last           # Son session'a devam
hackeragent --resume 20260420-...   # Belirli session ID
hackeragent --list-sessions         # Tüm session'ları listele

# Sadece araçları listele
hackeragent --list-tools

# Özel config + debug log
hackeragent --config my-config.yaml --log-level DEBUG
```

### 🛡️ Güvenlik Özellikleri (Phase A)

| Özellik | Açıklama |
|---|---|
| **Scope enforcement** | Scope dışı host'lara yapılan tool çağrıları bloklanır. OSINT servisleri (crt.sh, shodan, github vb.) otomatik allowlist'te. |
| **Cost guardrail** | `max_session_cost_usd` aşılırsa döngü otomatik durur. OpenRouter'ın `usage.cost` alanından gerçek-zamanlı takip. |
| **Session persistence** | Her turda `~/.hackeragent/sessions/<id>.json` — çökme sonrası `--resume last` ile devam. |
| **Streaming yanıt** | Token-token ekrana yazılır — uzun Hermes yanıtlarını beklemezsiniz. UTF-8 multi-byte güvenli. |
| **Structured parsers** | `nmap_scan_structured` ve `sqlmap_test_structured` → LLM raw çıktı parse etmek yerine yapılandırılmış JSON alır (daha doğru finding'ler). |

---

## 📁 Dosya Yapısı

```
HackerAgent/
├── hackeragent/                  # 🧠 Ana Python paketi (orkestratör)
│   ├── __main__.py               # python -m hackeragent
│   ├── core/
│   │   ├── orchestrator.py       # OODA Loop motoru
│   │   ├── llm_client.py         # OpenRouter client (tool use)
│   │   ├── mcp_manager.py        # MCP server lifecycle (stdio)
│   │   ├── tool_router.py        # tool_calls → MCP çağrıları
│   │   ├── prompt_engine.py      # system_prompt + rules + skills
│   │   └── config.py             # YAML + .env yükleyici
│   ├── cli/
│   │   ├── main.py               # argparse + REPL
│   │   └── banner.py
│   └── utils/logger.py
│
├── config.yaml                   # 🎛️ Merkezi konfigürasyon
├── .env.example                  # Örnek environment variables
├── system_prompt.md              # 🧠 Hacker persona & metodoloji
├── pyproject.toml                # Python paketi
├── requirements.txt
│
├── rules/                        # 📜 Operasyonel kurallar
│   ├── scope-guard.md
│   └── safety-rules.md
│
├── skills/                       # ⚡ 6 güvenlik skill'i
│   ├── recon-enumeration/
│   ├── web-exploit/
│   ├── binary-pwn/
│   ├── crypto-forensics/
│   ├── ctf-solver/
│   └── report-generator/
│
├── mcp-servers/                  # ⚙️ 5 MCP server
│   ├── mcp-kali-tools/
│   ├── mcp-ctf-platform/
│   ├── mcp-memory-server/
│   ├── mcp-telemetry/
│   └── mcp-rag-engine/
│
├── scripts/                      # 🔄 Yardımcı scriptler
│   ├── attack_planner.py
│   ├── recon_daemon.py
│   └── swarm_orchestrator.py
│
├── workflows/                    # 📋 İş akışları
│   ├── bug-bounty-workflow.md
│   ├── ctf-workflow.md
│   └── supervisor-workflow.md
│
└── install.sh                    # 🚀 Tek komut kurulum
```

---

## 🔧 Konfigürasyon

### `.env` (hassas)
```bash
OPENROUTER_API_KEY=sk-or-v1-...
CTFD_URL=https://ctfd.example.com
CTFD_TOKEN=...
HTB_TOKEN=...
```

### `config.yaml` veya `~/.hackeragent/config.yaml` (ayarlar)
```yaml
llm:
  models:
    orchestrator: "qwen/qwen3.6-plus"
    exploit_gen: "nousresearch/hermes-4-405b"
  temperature: 0.3
  max_tool_iterations: 25

mcp_servers:
  rag-engine:
    enabled: false   # tekil server'ı kapatmak için
```

**Öncelik sırası:** `OPENROUTER_API_KEY` env var → `~/.hackeragent/config.yaml` → repo içindeki `config.yaml` → built-in varsayılanlar.

---

## 🔀 v2.0'dan Geçiş

- **Silindi:** `setup_openrouter.sh`, `~/.claude/settings.json`, Claude Code CLI, Node.js, `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS`, `ANTHROPIC_BASE_URL` hile'si.
- **Değişti:** `~/.claude/` → `~/.hackeragent/` (veri dizini). Eski path hala okunur (geriye uyumluluk) ama yeni yazımlar yeni konuma gider.
- **Değişti:** `CLAUDE.md` → `system_prompt.md`. `.claude/rules/` → `rules/`.
- **Eklendi:** `hackeragent` CLI, `config.yaml`, `pyproject.toml`, `.env.example`.

---

## ⚠️ Yasal Uyarı

Bu sistem **yalnızca yasal ve etik** güvenlik testi amaçlarıyla kullanılmalıdır:

- ✅ Yazılı izin aldığınız hedefleri test edin
- ✅ Bug bounty program kurallarına uyun
- ✅ CTF yarışmalarında sportif davranın
- ✅ Zafiyetleri sorumlu şekilde raporlayın
- ❌ Yetkisiz hedeflere saldırmayın
- ❌ Bulunan verileri kötüye kullanmayın

---

## 📊 Kapsam

- **200+ zafiyet tipi** (Web, Binary, Crypto, Forensics)
- **150+ hazır payload** (SQLi, XSS, SSRF, LFI, CMDi, SSTI)
- **40+ araç** MCP üzerinden
- **2 LLM modeli** (Qwen 3.6 Plus + Hermes 4 405B)
- **7 CTF kategorisi** için prosedürler
- **CVSS hesaplama** ve rapor şablonları
- **Kill Chain + OODA Loop** metodolojisi
- **Kalıcı hafıza** (SQLite + NetworkX knowledge graph)
- **RAG bilgi tabanı** (ChromaDB)

---

*Developed for ethical security research and CTF competitions.*
