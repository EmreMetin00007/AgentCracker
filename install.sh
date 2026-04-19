#!/bin/bash
# ============================================================
# 🔴 HackerAgent — Kali Linux TEK KOMUT KURULUM
# ============================================================
# GitHub'dan klonladıktan sonra bu scripti çalıştır:
#
#   git clone https://github.com/KULLANICI/HackerAgent.git
#   cd HackerAgent
#   chmod +x install.sh
#   sudo ./install.sh
#
# Bu script:
#   1. Tüm Kali güvenlik araçlarını kurar
#   2. Python bağımlılıklarını kurar
#   3. Skills'leri Claude Code dizinine kopyalar
#   4. MCP server'ları yapılandırır
#   5. Global CLAUDE.md'yi ayarlar
#   6. Her şeyi doğrular
# ============================================================

set -e

# Renkler
R='\033[0;31m'
G='\033[0;32m'
Y='\033[1;33m'
C='\033[0;36m'
B='\033[1;37m'
N='\033[0m'

# Repo dizini (bu script nerede çalıştırılıyorsa)
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

# Kullanıcı tespiti (sudo ile çalışıyorsa gerçek kullanıcıyı bul)
if [ -n "$SUDO_USER" ]; then
    REAL_USER="$SUDO_USER"
    REAL_HOME=$(eval echo "~$SUDO_USER")
else
    REAL_USER="$USER"
    REAL_HOME="$HOME"
fi

# Claude Code skill dizini
SKILLS_DIR="$REAL_HOME/.gemini/antigravity/skills"

# Claude Code settings dizini
CLAUDE_DIR="$REAL_HOME/.claude"

# MCP server mutlak yolları
MCP_KALI_PATH="$REPO_DIR/mcp-servers/mcp-kali-tools/server.py"
MCP_CTF_PATH="$REPO_DIR/mcp-servers/mcp-ctf-platform/server.py"
MCP_MEMORY_PATH="$REPO_DIR/mcp-servers/mcp-memory-server/server.py"
MCP_TELEMETRY_PATH="$REPO_DIR/mcp-servers/mcp-telemetry/server.py"

echo -e "${R}"
cat << 'BANNER'
  ╔══════════════════════════════════════════════╗
  ║                                              ║
  ║   🔴  H A C K E R   A G E N T              ║
  ║                                              ║
  ║   Autonomous Bug Bounty & CTF Solver         ║
  ║   Claude Code × Kali Linux                   ║
  ║                                              ║
  ╚══════════════════════════════════════════════╝
BANNER
echo -e "${N}"

echo -e "${B}Kullanıcı: $REAL_USER${N}"
echo -e "${B}Home: $REAL_HOME${N}"
echo -e "${B}Repo: $REPO_DIR${N}"
echo -e "${B}Skills: $SKILLS_DIR${N}"
echo ""

# ============================================================
# PHASE 0: ÖN KOŞULLAR — Node.js & Claude Code
# ============================================================
echo -e "${C}━━━ [0/7] Ön koşullar kontrol ediliyor... ━━━${N}"

# Node.js kurulumu (Claude Code için gerekli)
if ! command -v node &> /dev/null; then
    echo -e "${Y}Node.js bulunamadı, kuruluyor (v20.x LTS)...${N}"
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - 2>/dev/null
    apt install -y -qq nodejs 2>/dev/null
else
    NODE_VER=$(node --version)
    echo -e "  ${G}✓${N} Node.js zaten kurulu: $NODE_VER"
fi

# npm kontrolü
if ! command -v npm &> /dev/null; then
    echo -e "${Y}npm bulunamadı, kuruluyor...${N}"
    apt install -y -qq npm 2>/dev/null
fi

# Claude Code CLI kurulumu
if ! command -v claude &> /dev/null; then
    echo -e "${Y}Claude Code kuruluyor (npm global)...${N}"
    npm install -g @anthropic-ai/claude-code 2>/dev/null || {
        echo -e "${R}Claude Code npm ile kurulamadı. Manuel kurulum gerekli.${N}"
        echo -e "${C}Bkz: https://docs.anthropic.com/claude-code${N}"
    }
else
    echo -e "  ${G}✓${N} Claude Code zaten kurulu: $(claude --version 2>/dev/null || echo 'mevcut')"
fi

echo -e "${G}[✓] Ön koşullar hazır${N}"

# ============================================================
# PHASE 1: SİSTEM ARAÇLARI
# ============================================================
echo -e "${C}━━━ [1/7] Sistem araçları kuruluyor... ━━━${N}"

apt update -y -qq

# Network & Recon
apt install -y -qq nmap masscan 2>/dev/null
apt install -y -qq gobuster 2>/dev/null
apt install -y -qq ffuf 2>/dev/null
apt install -y -qq feroxbuster 2>/dev/null || true
apt install -y -qq subfinder 2>/dev/null || true
apt install -y -qq amass 2>/dev/null || true
apt install -y -qq httpx-toolkit 2>/dev/null || true
apt install -y -qq whatweb wafw00f 2>/dev/null
apt install -y -qq dnsutils whois curl wget 2>/dev/null
apt install -y -qq netcat-openbsd 2>/dev/null
apt install -y -qq theharvester 2>/dev/null || true

# Web Exploitation
apt install -y -qq sqlmap nikto 2>/dev/null
apt install -y -qq wpscan 2>/dev/null || true
apt install -y -qq nuclei 2>/dev/null || true
apt install -y -qq joomscan 2>/dev/null || true
apt install -y -qq arjun 2>/dev/null || true

# Password Cracking
apt install -y -qq hashcat john 2>/dev/null
apt install -y -qq fcrackzip 2>/dev/null

# Forensics & Steg
apt install -y -qq binwalk foremost 2>/dev/null
apt install -y -qq libimage-exiftool-perl 2>/dev/null  # exiftool
apt install -y -qq steghide 2>/dev/null
apt install -y -qq wireshark-common tshark 2>/dev/null
apt install -y -qq volatility3 2>/dev/null || true

# Binary & RE
apt install -y -qq gdb 2>/dev/null
apt install -y -qq radare2 2>/dev/null
apt install -y -qq ghidra 2>/dev/null || true

# SMB/LDAP
apt install -y -qq enum4linux smbclient 2>/dev/null
apt install -y -qq crackmapexec 2>/dev/null || true

# Misc
apt install -y -qq git python3 python3-pip python3-venv 2>/dev/null
apt install -y -qq ruby ruby-dev 2>/dev/null
apt install -y -qq hydra 2>/dev/null

echo -e "${G}[✓] Sistem araçları kuruldu${N}"

# ============================================================
# PHASE 2: WORDLIST'LER
# ============================================================
echo -e "${C}━━━ [2/7] Wordlist'ler kuruluyor... ━━━${N}"

apt install -y -qq seclists 2>/dev/null || true
apt install -y -qq wordlists 2>/dev/null || true

# rockyou.txt'yi aç
if [ -f /usr/share/wordlists/rockyou.txt.gz ]; then
    cd /usr/share/wordlists
    gunzip -kf rockyou.txt.gz 2>/dev/null || true
    cd "$REPO_DIR"
fi

echo -e "${G}[✓] Wordlist'ler hazır${N}"

# ============================================================
# PHASE 3: PYTHON BAĞIMLILIKLARI
# ============================================================
echo -e "${C}━━━ [3/7] Python bağımlılıkları kuruluyor... ━━━${N}"

PIP_ARGS="--ignore-installed"
# Python 3.11+ externally managed ortamlar için
if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
    PIP_ARGS="--ignore-installed --break-system-packages"
fi

pip3 install $PIP_ARGS --quiet mcp[cli] 2>/dev/null || pip3 install $PIP_ARGS mcp[cli]
pip3 install $PIP_ARGS --quiet pwntools 2>/dev/null || pip3 install $PIP_ARGS pwntools
pip3 install $PIP_ARGS --quiet requests 2>/dev/null || pip3 install $PIP_ARGS requests
pip3 install $PIP_ARGS --quiet pycryptodome 2>/dev/null || true
pip3 install $PIP_ARGS --quiet z3-solver 2>/dev/null || true
pip3 install $PIP_ARGS --quiet sympy 2>/dev/null || true
pip3 install $PIP_ARGS --quiet Pillow 2>/dev/null || true
pip3 install $PIP_ARGS --quiet scapy 2>/dev/null || true
pip3 install $PIP_ARGS --quiet ROPgadget 2>/dev/null || true
pip3 install $PIP_ARGS --quiet ropper 2>/dev/null || true
pip3 install $PIP_ARGS --quiet owiener 2>/dev/null || true
pip3 install $PIP_ARGS --quiet ciphey 2>/dev/null || true

# v2.0: Güvenlik ve Observability katmanı
pip3 install $PIP_ARGS --quiet keyring 2>/dev/null || true

# v2.0: Knowledge Graph + Attack Path Planner
pip3 install $PIP_ARGS --quiet networkx 2>/dev/null || true

# v2.0: Phase 3 — Yeni araç bağımlılıkları
pip3 install $PIP_ARGS --quiet trufflehog 2>/dev/null || true
pip3 install $PIP_ARGS --quiet impacket 2>/dev/null || true
pip3 install $PIP_ARGS --quiet frida-tools 2>/dev/null || true
pip3 install $PIP_ARGS --quiet objection 2>/dev/null || true
pip3 install $PIP_ARGS --quiet mitmproxy 2>/dev/null || true
pip3 install $PIP_ARGS --quiet bloodhound 2>/dev/null || true

# v2.0: Phase 4 — RAG Engine
pip3 install $PIP_ARGS --quiet chromadb 2>/dev/null || true

# v2.0: Phase 7 — Headless Browser & JS Analysis
echo -e "${C}Phase 7: Headless browser & JS analysis araçları kuruluyor...${N}"
pip3 install $PIP_ARGS --quiet playwright 2>/dev/null || true
pip3 install $PIP_ARGS --quiet beautifulsoup4 2>/dev/null || true
su - "$REAL_USER" -c 'playwright install chromium 2>/dev/null' || true
echo -e "  ${G}✓${N} Playwright + Chromium"

# angr (büyük paket, opsiyonel)
echo -e "${C}angr kurulumu (symbolic execution, büyük paket)...${N}"
pip3 install $PIP_ARGS --quiet angr 2>/dev/null || echo -e "  ${Y}⚠ angr kurulamadı (opsiyonel)${N}"

echo -e "${G}[✓] Python bağımlılıkları kuruldu${N}"

# v2.0: Go araçları (Phase 3 + Phase 7)
echo -e "${C}Go araçları kuruluyor...${N}"
if command -v go &>/dev/null; then
    go install github.com/lc/gau/v2/cmd/gau@latest 2>/dev/null || true
    go install github.com/tomnomnom/waybackurls@latest 2>/dev/null || true
    go install github.com/assetnote/kiterunner/cmd/kr@latest 2>/dev/null || true
    # Phase 7: Blind vulnerability detection & Subdomain takeover
    go install -v github.com/projectdiscovery/interactsh/cmd/interactsh-client@latest 2>/dev/null || true
    go install github.com/haccer/subjack@latest 2>/dev/null || true
    echo -e "${G}[✓] Go araçları kuruldu (gau, waybackurls, kiterunner, interactsh, subjack)${N}"
else
    echo -e "${Y}[!] Go kurulu değil, Go araçları atlanıyor${N}"
fi

# v2.0: Sistem araçları (Phase 3 + Phase 7)
apt install -y -qq gitleaks tesseract-ocr cutycapt wkhtmltopdf 2>/dev/null || true
apt install -y -qq nodejs-js-beautify 2>/dev/null || npm install -g js-beautify 2>/dev/null || true

# ============================================================
# PHASE 4: GDB EKLENTİLERİ & RUBY GEM'LERİ
# ============================================================
echo -e "${C}━━━ [4/7] GDB eklentileri & Ruby gem'leri... ━━━${N}"

# GEF (GDB Enhanced Features)
if [ ! -f "$REAL_HOME/.gdbinit-gef.py" ]; then
    su - "$REAL_USER" -c 'bash -c "$(curl -fsSL https://gef.blah.cat/sh)"' 2>/dev/null || true
fi

# one_gadget
gem install one_gadget 2>/dev/null || true

echo -e "${G}[✓] GDB eklentileri & gem'ler kuruldu${N}"

# ============================================================
# PHASE 5: SKILLS KURULUMU
# ============================================================
echo -e "${C}━━━ [5/7] Claude Code skills kuruluyor... ━━━${N}"

# Skills dizinini oluştur
su - "$REAL_USER" -c "mkdir -p '$SKILLS_DIR'" 2>/dev/null || mkdir -p "$SKILLS_DIR"

# Her skill'i kopyala
SKILL_LIST="recon-enumeration web-exploit binary-pwn crypto-forensics ctf-solver report-generator"

for skill in $SKILL_LIST; do
    SRC="$REPO_DIR/skills/$skill"
    DST="$SKILLS_DIR/$skill"
    
    if [ -d "$SRC" ]; then
        # Eski varsa sil, yenisini kopyala
        rm -rf "$DST" 2>/dev/null || true
        cp -r "$SRC" "$DST"
        chown -R "$REAL_USER:$REAL_USER" "$DST"
        echo -e "  ${G}✓${N} $skill"
    else
        echo -e "  ${R}✗${N} $skill (kaynak bulunamadı: $SRC)"
    fi
done

echo -e "${G}[✓] Skills kuruldu: $SKILLS_DIR${N}"

# ============================================================
# PHASE 6: MCP SERVER & CLAUDE CODE YAPILANDIRMASI
# ============================================================
echo -e "${C}━━━ [6/7] MCP server'lar ve Claude Code yapılandırılıyor... ━━━${N}"

# Claude dizini
su - "$REAL_USER" -c "mkdir -p '$CLAUDE_DIR'" 2>/dev/null || mkdir -p "$CLAUDE_DIR"

# OpenRouter API Key Sor (Qwen 3.6 Plus + Hermes 405B Entegrasyonu)
echo -e ""
echo -e "${Y}Hibrit LLM Mimarisi — OpenRouter API Entegrasyonu${N}"
echo -e "${C}Aynı API key ile 2 model kullanılır:${N}"
echo -e "${C}  📊 Qwen 3.6 Plus  → Derin zafiyet/trafik/kod analizi${N}"
echo -e "${C}  🔓 Hermes 405B    → Sansürsüz exploit payload üretimi${N}"
read -p "OpenRouter API Key'inizi girin (Kullanmayacaksanız boş bırakıp Enter'a basın): " openrouter_key
echo -e ""

# .claude/settings.json — Global MCP server tanımları (v2.0: +telemetry +rag-engine)
cat > "$CLAUDE_DIR/settings.json" << SETTINGS_EOF
{
  "openrouter_api_key": "$openrouter_key",
  "mcpServers": {
    "kali-tools": {
      "command": "python3",
      "args": ["$MCP_KALI_PATH"],
      "env": {}
    },
    "ctf-platform": {
      "command": "python3",
      "args": ["$MCP_CTF_PATH"],
      "env": {
        "CTFD_URL": "",
        "CTFD_TOKEN": "",
        "HTB_TOKEN": "",
        "THM_TOKEN": ""
      }
    },
    "memory-server": {
      "command": "python3",
      "args": ["$MCP_MEMORY_PATH"],
      "env": {}
    },
    "telemetry": {
      "command": "python3",
      "args": ["$MCP_TELEMETRY_PATH"],
      "env": {}
    },
    "rag-engine": {
      "command": "python3",
      "args": ["$REPO_DIR/mcp-servers/mcp-rag-engine/server.py"],
      "env": {}
    }
  }
}
SETTINGS_EOF
chown "$REAL_USER:$REAL_USER" "$CLAUDE_DIR/settings.json"

# Approval dizini oluştur (Human-in-the-Loop)
mkdir -p "$CLAUDE_DIR/approvals"
chown -R "$REAL_USER:$REAL_USER" "$CLAUDE_DIR/approvals"

# Global CLAUDE.md (ana persona)
cp "$REPO_DIR/CLAUDE.md" "$REAL_HOME/CLAUDE.md"
chown "$REAL_USER:$REAL_USER" "$REAL_HOME/CLAUDE.md"

# Proje dizinine de .claude/rules kopyala
mkdir -p "$REPO_DIR/.claude/rules"
if [ ! -f "$REPO_DIR/.claude/rules/scope-guard.md" ]; then
    cat > "$REPO_DIR/.claude/rules/scope-guard.md" << 'SCOPE_EOF'
# Scope Guard — Hedef Koruma Kuralları

## Zorunlu Kurallar
1. Sadece açıkça belirtilen hedefler üzerinde çalış
2. Scope dışı hedeflere ASLA istek gönderme
3. Hedef değişikliği için kullanıcı onayı gerekli
4. Üçüncü parti servislere (GitHub, Google vb.) yapılan OSINT sorguları hariç
5. Her yeni hedef için scope doğrulaması yap

## Hedef Kapsamı
- Kullanıcı tarafından verilen IP, domain veya URL'ler scope dahilindedir
- Wildcard scope (*.target.com) belirtilmedikçe subdomain'ler hariçtir
- Internal IP aralıkları (10.x, 172.16-31.x, 192.168.x) sadece lab/CTF ortamlarında geçerlidir
SCOPE_EOF
fi

if [ ! -f "$REPO_DIR/.claude/rules/safety-rules.md" ]; then
    cat > "$REPO_DIR/.claude/rules/safety-rules.md" << 'SAFETY_EOF'
# Safety Rules — Operasyonel Güvenlik

## Credential Yönetimi
- Bulunan şifreleri/token'ları ASLA loglama veya üçüncü partiye gönderme
- Session token'ları scope dışında kullanma
- API key'leri düz metin olarak saklamaktan kaçın

## Destruktif Operasyonlar
- DELETE/DROP/TRUNCATE komutları için kullanıcı onayı gerekli
- Dosya silme, veritabanı değiştirme operasyonları onay ister
- DDoS veya servis kesintisi yaratabilecek testler yasak (aksi belirtilmedikçe)

## Operasyonel Güvenlik
- Exploit çalıştırmadan önce reversibility kontrolü yap
- Her kritik adımda checkpoint oluştur
- Hata durumunda güvenli durma (graceful stop)
SAFETY_EOF
fi

echo -e "${G}[✓] MCP server'lar ve Claude Code yapılandırıldı${N}"

# ============================================================
# PHASE 7: DOĞRULAMA
# ============================================================
echo -e "${C}━━━ [7/7] Kurulum doğrulanıyor... ━━━${N}"
echo ""

PASS=0
FAIL=0

check_tool() {
    if command -v "$1" &> /dev/null; then
        echo -e "  ${G}✓${N} $1"
        ((PASS++))
    else
        echo -e "  ${R}✗${N} $1"
        ((FAIL++))
    fi
}

check_file() {
    if [ -e "$1" ]; then
        echo -e "  ${G}✓${N} $2"
        ((PASS++))
    else
        echo -e "  ${R}✗${N} $2"
        ((FAIL++))
    fi
}

echo -e "${Y}── Ön Koşullar ──${N}"
check_tool node
check_tool npm
check_tool claude

echo -e "${Y}── Ağ & Keşif ──${N}"
check_tool nmap
check_tool gobuster
check_tool ffuf
check_tool subfinder
check_tool whatweb
check_tool wafw00f
check_tool masscan

echo -e "${Y}── Web Exploitation ──${N}"
check_tool sqlmap
check_tool nikto
check_tool wpscan
check_tool nuclei
check_tool hydra

echo -e "${Y}── Password Cracking ──${N}"
check_tool hashcat
check_tool john
check_tool fcrackzip

echo -e "${Y}── Forensics ──${N}"
check_tool binwalk
check_tool foremost
check_tool exiftool
check_tool steghide
check_tool tshark

echo -e "${Y}── Binary / RE ──${N}"
check_tool gdb
check_tool r2
check_tool checksec

echo -e "${Y}── Python ──${N}"
check_tool python3
python3 -c "import pwn" 2>/dev/null && { echo -e "  ${G}✓${N} pwntools"; ((PASS++)); } || { echo -e "  ${R}✗${N} pwntools"; ((FAIL++)); }
python3 -c "import mcp" 2>/dev/null && { echo -e "  ${G}✓${N} mcp"; ((PASS++)); } || { echo -e "  ${R}✗${N} mcp"; ((FAIL++)); }

echo -e "${Y}── Wordlist'ler ──${N}"
check_file "/usr/share/wordlists/rockyou.txt" "rockyou.txt"
check_file "/usr/share/seclists" "seclists"

echo -e "${Y}── HackerAgent Dosyaları ──${N}"
check_file "$REAL_HOME/CLAUDE.md" "Global CLAUDE.md"
check_file "$CLAUDE_DIR/settings.json" "MCP Settings"
for skill in $SKILL_LIST; do
    check_file "$SKILLS_DIR/$skill/SKILL.md" "Skill: $skill"
done
check_file "$MCP_KALI_PATH" "MCP: kali-tools"
check_file "$MCP_CTF_PATH" "MCP: ctf-platform"
check_file "$MCP_MEMORY_PATH" "MCP: memory-server"
check_file "$MCP_TELEMETRY_PATH" "MCP: telemetry"

echo -e "${Y}── v2.0 Güvenlik ──${N}"
check_file "$CLAUDE_DIR/approvals" "Approval dizini"
check_file "$REPO_DIR/.claude/rules/safety-rules.md" "Safety Rules v2.0"
python3 -c "import keyring" 2>/dev/null && { echo -e "  ${G}✓${N} keyring"; ((PASS++)); } || { echo -e "  ${R}✗${N} keyring (opsiyonel)"; }

echo ""
echo -e "${B}════════════════════════════════════${N}"
echo -e "  ${G}Başarılı: $PASS${N}  |  ${R}Başarısız: $FAIL${N}"
echo -e "${B}════════════════════════════════════${N}"

echo ""
echo -e "${R}╔══════════════════════════════════════════════╗${N}"
echo -e "${R}║                                              ║${N}"
echo -e "${R}║   🔴 HackerAgent KURULUM TAMAMLANDI!        ║${N}"
echo -e "${R}║                                              ║${N}"
echo -e "${R}╚══════════════════════════════════════════════╝${N}"
echo ""
echo -e "${Y}Kullanım:${N}"
echo -e "  ${B}cd $REPO_DIR${N}"
echo -e "  ${B}claude${N}"
echo -e ""
echo -e "${Y}İlk komutlarınız:${N}"
echo -e "  ${C}→ \"10.10.10.10 hedefini tara\"${N}"
echo -e "  ${C}→ \"Bu CTF challenge'ını çöz\"${N}"
echo -e "  ${C}→ \"example.com üzerinde bug bounty yap\"${N}"
echo ""
echo -e "${Y}CTF Platform API (opsiyonel):${N}"
echo -e "  ${C}$CLAUDE_DIR/settings.json dosyasını düzenleyin${N}"
echo -e "  ${C}CTFD_URL, CTFD_TOKEN, HTB_TOKEN değerlerini girin${N}"
echo ""
echo -e "${R}⚠️  Sadece yetkili hedefler üzerinde kullanın!${N}"
echo ""
