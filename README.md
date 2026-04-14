# 🔴 HackerAgent

**Claude Code × Kali Linux = Otonom Bug Bounty Avcısı & CTF Çözücü**

Claude Code'u Kali Linux üzerinde profesyonel, tam otonom bir güvenlik araştırmacısına dönüştüren sistem. Kill Chain metodolojisi, OODA Loop karar döngüsü ve 200+ zafiyet tipi ile donatılmış.

## ⚡ Tek Komutla Kurulum

```bash
# 1. Kali Linux'ta repoyu klonla
git clone https://github.com/KULLANICI/HackerAgent.git

# 2. Dizine gir
cd HackerAgent

# 3. Kurulum scriptini çalıştır (her şeyi yapar)
chmod +x install.sh
sudo ./install.sh

# 4. Claude Code'u başlat
claude
```

**Bu kadar.** `install.sh` aşağıdakileri otomatik yapar:
- ✅ Tüm Kali güvenlik araçlarını kurar (nmap, sqlmap, ffuf, nuclei, hashcat, john, gdb, binwalk...)
- ✅ Python bağımlılıklarını kurar (pwntools, mcp, z3, cryptodome...)
- ✅ Wordlist'leri hazırlar (rockyou.txt, seclists)
- ✅ 6 güvenlik skill'ini Claude Code'a yükler
- ✅ 2 MCP server'ı yapılandırır
- ✅ Global CLAUDE.md persona dosyasını kurar
- ✅ GDB eklentilerini (GEF) ve Ruby gem'lerini kurar

---

## 🏗️ Ne İçeriyor?

### 🧠 Hacker Persona (CLAUDE.md)
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

### ⚙️ 2 MCP Server

| Server | Araçlar |
|--------|---------|
| `kali-tools` | 25+ araç: nmap, ffuf, sqlmap, nikto, nuclei, hydra, hashcat, john, volatility... |
| `ctf-platform` | CTFd, HackTheBox, TryHackMe API + decode/hash yardımcıları |

### 📋 İş Akışları
- **Bug Bounty Workflow** — 6 fazlı profesyonel süreç
- **CTF Workflow** — Kategori bazlı çözüm prosedürleri

---

## 🎯 Kullanım Örnekleri

```bash
# Claude Code'u başlat
claude

# Hedef tarama
> "10.10.10.10 hedefini tara ve zafiyetleri bul"

# Bug bounty
> "example.com üzerinde kapsamlı güvenlik testi yap"

# CTF challenge çözme
> "Bu binary dosyasını analiz et ve exploit yaz"
> "Bu PCAP dosyasını analiz et, flag'i bul"
> "Bu şifreli metni kır"

# Rapor oluşturma
> "Bulduğum SQL injection için HackerOne raporu yaz"
```

---

## 📁 Dosya Yapısı

```
HackerAgent/
├── install.sh                 # 🚀 Tek komut kurulum
├── CLAUDE.md                  # 🧠 Hacker persona & metodoloji
├── .gitignore
├── .claude/
│   └── rules/
│       ├── scope-guard.md     # Hedef koruma kuralları
│       └── safety-rules.md    # Operasyonel güvenlik
├── skills/                    # ⚡ 6 güvenlik skill'i
│   ├── recon-enumeration/
│   │   ├── SKILL.md
│   │   └── references/
│   ├── web-exploit/
│   │   ├── SKILL.md
│   │   └── references/payloads.md
│   ├── binary-pwn/
│   │   ├── SKILL.md
│   │   └── scripts/exploit_template.py
│   ├── crypto-forensics/
│   │   └── SKILL.md
│   ├── ctf-solver/
│   │   ├── SKILL.md
│   │   └── references/ctf-methodology.md
│   └── report-generator/
│       ├── SKILL.md
│       └── templates/report-templates.md
├── mcp-servers/               # ⚙️ MCP server'lar
│   ├── mcp-kali-tools/
│   │   ├── server.py
│   │   └── requirements.txt
│   └── mcp-ctf-platform/
│       ├── server.py
│       └── requirements.txt
└── workflows/                 # 📋 İş akışları
    ├── bug-bounty-workflow.md
    └── ctf-workflow.md
```

---

## 🔧 CTF Platform API (Opsiyonel)

CTF platformlarına API erişimi için `~/.claude/settings.json` dosyasındaki token'ları doldurun:

```bash
# Dosyayı düzenle
nano ~/.claude/settings.json

# CTFd:  CTFD_URL ve CTFD_TOKEN değerlerini girin
# HTB:   HTB_TOKEN değerini girin  
# THM:   THM_TOKEN değerini girin
```

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
- **25+ araç** MCP üzerinden
- **7 CTF kategorisi** için prosedürler
- **CVSS hesaplama** ve rapor şablonları
- **Kill Chain + OODA Loop** metodolojisi

---

*Developed for ethical security research and CTF competitions.*
