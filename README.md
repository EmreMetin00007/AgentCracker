# 🔴 HackerAgent v3.0

**Otonom Bug Bounty Avcısı & CTF Çözücü — Claude Code CLI'dan Bağımsız**

HackerAgent, OpenRouter (Qwen 3.6 Plus + Hermes 405B) üzerinde çalışan kendi
orkestratörüne sahip bağımsız bir güvenlik platformudur. MCP (Model Context
Protocol) mimarisini koruyarak Kali Linux güvenlik araçlarına, knowledge
graph hafızasına, RAG bilgi tabanına ve telemetriye tek bir CLI üzerinden
erişir. Kill Chain metodolojisi, OODA Loop karar döngüsü ve 200+ zafiyet tipi
ile donatılmıştır.

> **v2.0 → v3.0 değişikliği:** Claude Code CLI bağımlılığı tamamen kaldırıldı.
> Artık Node.js, `npm install -g @anthropic-ai/claude-code` veya
> `~/.claude/settings.json` yok. `hackeragent` komutu kendi Python orkestratörünü
> çalıştırır; MCP server'lar aynen korunmuştur.

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
# İnteraktif REPL
hackeragent

# REPL içinde:
> 10.10.10.10 hedefini tara ve zafiyetleri bul
> example.com üzerinde kapsamlı güvenlik testi yap
> Bu binary dosyasını analiz et ve exploit yaz
> Bulduğum SQL injection için HackerOne raporu yaz

# REPL komutları:
/tools      # Aktif MCP araçlarını listele
/reset      # Sohbet geçmişini sıfırla
/exit       # Çık
```

```bash
# Tek görev (REPL açmadan)
hackeragent --task "10.10.10.10 portlarını tara"

# Sadece araçları listele
hackeragent --list-tools

# Özel config
hackeragent --config my-config.yaml

# Debug logları
hackeragent --log-level DEBUG
```

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
