#!/bin/bash
# ============================================================
# 🔴 HackerAgent v3.0 — Kali Linux TEK KOMUT KURULUM
# ============================================================
# GitHub'dan klonladıktan sonra bu scripti çalıştır:
#
#   git clone https://github.com/KULLANICI/HackerAgent.git
#   cd HackerAgent
#   chmod +x install.sh
#   sudo ./install.sh
#
# Bu script:
#   1. Kali güvenlik araçlarını kurar (nmap, sqlmap, ffuf, ...)
#   2. Python bağımlılıklarını + hackeragent paketini kurar
#   3. Wordlist'leri hazırlar
#   4. ~/.hackeragent veri dizinini oluşturur
#   5. OpenRouter API key'i .env dosyasına kaydeder
#   6. Her şeyi doğrular
#
# Claude Code CLI ve Node.js GEREKMEZ — hackeragent bağımsız çalışır.
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

# HackerAgent veri dizini
HACKERAGENT_HOME="$REAL_HOME/.hackeragent"

echo -e "${R}"
cat << 'BANNER'
  ╔══════════════════════════════════════════════╗
  ║                                              ║
  ║   🔴  H A C K E R   A G E N T   v3.0        ║
  ║                                              ║
  ║   Autonomous Bug Bounty & CTF Solver         ║
  ║   OpenRouter × MCP × Kali Linux              ║
  ║                                              ║
  ╚══════════════════════════════════════════════╝
BANNER
echo -e "${N}"

echo -e "${B}Kullanıcı: $REAL_USER${N}"
echo -e "${B}Home: $REAL_HOME${N}"
echo -e "${B}Repo: $REPO_DIR${N}"
echo -e "${B}Veri Dizini: $HACKERAGENT_HOME${N}"
echo ""

# ============================================================
# PHASE 1: SİSTEM ARAÇLARI
# ============================================================
echo -e "${C}━━━ [1/6] Sistem araçları kuruluyor... ━━━${N}"

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
echo -e "${C}━━━ [2/6] Wordlist'ler kuruluyor... ━━━${N}"

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
# PHASE 3: PYTHON BAĞIMLILIKLARI + HACKERAGENT PAKETİ
# ============================================================
echo -e "${C}━━━ [3/6] Python bağımlılıkları kuruluyor... ━━━${N}"

PIP_ARGS="--ignore-installed"
# Python 3.11+ externally managed ortamlar için
if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
    PIP_ARGS="--ignore-installed --break-system-packages"
fi

# hackeragent paketi (tüm core + MCP client bağımlılıklarını çeker)
pip3 install $PIP_ARGS --quiet -e "$REPO_DIR" 2>/dev/null || pip3 install $PIP_ARGS -e "$REPO_DIR"

# Güvenlik tool'ları için ek paketler
pip3 install $PIP_ARGS --quiet pwntools 2>/dev/null || pip3 install $PIP_ARGS pwntools
pip3 install $PIP_ARGS --quiet pycryptodome 2>/dev/null || true
pip3 install $PIP_ARGS --quiet z3-solver 2>/dev/null || true
pip3 install $PIP_ARGS --quiet sympy 2>/dev/null || true
pip3 install $PIP_ARGS --quiet Pillow 2>/dev/null || true
pip3 install $PIP_ARGS --quiet scapy 2>/dev/null || true
pip3 install $PIP_ARGS --quiet ROPgadget 2>/dev/null || true
pip3 install $PIP_ARGS --quiet ropper 2>/dev/null || true
pip3 install $PIP_ARGS --quiet owiener 2>/dev/null || true
pip3 install $PIP_ARGS --quiet ciphey 2>/dev/null || true
pip3 install $PIP_ARGS --quiet keyring 2>/dev/null || true
pip3 install $PIP_ARGS --quiet trufflehog 2>/dev/null || true
pip3 install $PIP_ARGS --quiet impacket 2>/dev/null || true
pip3 install $PIP_ARGS --quiet frida-tools 2>/dev/null || true
pip3 install $PIP_ARGS --quiet objection 2>/dev/null || true
pip3 install $PIP_ARGS --quiet mitmproxy 2>/dev/null || true
pip3 install $PIP_ARGS --quiet bloodhound 2>/dev/null || true

# Headless browser & JS analysis
echo -e "${C}Headless browser & JS analysis araçları...${N}"
pip3 install $PIP_ARGS --quiet playwright 2>/dev/null || true
pip3 install $PIP_ARGS --quiet beautifulsoup4 2>/dev/null || true
su - "$REAL_USER" -c 'playwright install chromium 2>/dev/null' || true

# angr (büyük paket, opsiyonel)
echo -e "${C}angr kurulumu (symbolic execution, büyük paket, opsiyonel)...${N}"
pip3 install $PIP_ARGS --quiet angr 2>/dev/null || echo -e "  ${Y}⚠ angr kurulamadı (opsiyonel)${N}"

echo -e "${G}[✓] Python bağımlılıkları kuruldu${N}"

# Go araçları (opsiyonel)
echo -e "${C}Go araçları kuruluyor...${N}"
if command -v go &>/dev/null; then
    go install github.com/lc/gau/v2/cmd/gau@latest 2>/dev/null || true
    go install github.com/tomnomnom/waybackurls@latest 2>/dev/null || true
    go install github.com/assetnote/kiterunner/cmd/kr@latest 2>/dev/null || true
    go install -v github.com/projectdiscovery/interactsh/cmd/interactsh-client@latest 2>/dev/null || true
    go install github.com/haccer/subjack@latest 2>/dev/null || true
    echo -e "${G}[✓] Go araçları kuruldu${N}"
else
    echo -e "${Y}[!] Go kurulu değil, Go araçları atlanıyor${N}"
fi

# Sistem yardımcıları
apt install -y -qq gitleaks tesseract-ocr cutycapt wkhtmltopdf 2>/dev/null || true

# ============================================================
# PHASE 4: GDB EKLENTİLERİ & RUBY GEM'LERİ
# ============================================================
echo -e "${C}━━━ [4/6] GDB eklentileri & Ruby gem'leri... ━━━${N}"

if [ ! -f "$REAL_HOME/.gdbinit-gef.py" ]; then
    su - "$REAL_USER" -c 'bash -c "$(curl -fsSL https://gef.blah.cat/sh)"' 2>/dev/null || true
fi

gem install one_gadget 2>/dev/null || true

echo -e "${G}[✓] GDB eklentileri & gem'ler kuruldu${N}"

# ============================================================
# PHASE 5: HACKERAGENT VERİ DİZİNİ & KONFİGÜRASYON
# ============================================================
echo -e "${C}━━━ [5/6] HackerAgent veri dizini ve .env yapılandırılıyor... ━━━${N}"

# Veri dizinini oluştur
su - "$REAL_USER" -c "mkdir -p '$HACKERAGENT_HOME/logs' '$HACKERAGENT_HOME/approvals' '$HACKERAGENT_HOME/rag_db'" 2>/dev/null \
    || mkdir -p "$HACKERAGENT_HOME/logs" "$HACKERAGENT_HOME/approvals" "$HACKERAGENT_HOME/rag_db"
chown -R "$REAL_USER:$REAL_USER" "$HACKERAGENT_HOME"

# OpenRouter API Key
echo -e ""
echo -e "${Y}Hibrit LLM Mimarisi — OpenRouter API Entegrasyonu${N}"
echo -e "${C}Aynı API key ile 2 model kullanılır:${N}"
echo -e "${C}  📊 Qwen 3.6 Plus  → Orkestratör + analiz${N}"
echo -e "${C}  🔓 Hermes 405B    → PoC exploit üretimi${N}"
echo -e "${C}  🔗 Key al: https://openrouter.ai/keys${N}"
read -p "OpenRouter API Key'inizi girin (boş bırakabilirsiniz, sonra .env'e ekleyebilirsiniz): " openrouter_key
echo -e ""

# .env dosyasını oluştur
ENV_FILE="$REPO_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    cp "$REPO_DIR/.env.example" "$ENV_FILE"
fi
# API key'i inject et (varsa)
if [ -n "$openrouter_key" ]; then
    if grep -q "^OPENROUTER_API_KEY=" "$ENV_FILE"; then
        sed -i "s|^OPENROUTER_API_KEY=.*|OPENROUTER_API_KEY=$openrouter_key|" "$ENV_FILE"
    else
        echo "OPENROUTER_API_KEY=$openrouter_key" >> "$ENV_FILE"
    fi
    chmod 600 "$ENV_FILE"
    chown "$REAL_USER:$REAL_USER" "$ENV_FILE"
    echo -e "${G}[✓] API key .env dosyasına kaydedildi${N}"
else
    echo -e "${Y}[!] API key boş bırakıldı. Çalıştırmadan önce $ENV_FILE dosyasını düzenleyin.${N}"
fi

echo -e "${G}[✓] HackerAgent veri dizini ve konfigürasyon hazır${N}"

# ============================================================
# PHASE 6: DOĞRULAMA
# ============================================================
echo -e "${C}━━━ [6/6] Kurulum doğrulanıyor... ━━━${N}"
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

check_python() {
    if python3 -c "$1" 2>/dev/null; then
        echo -e "  ${G}✓${N} $2"
        ((PASS++))
    else
        echo -e "  ${R}✗${N} $2"
        ((FAIL++))
    fi
}

echo -e "${Y}── HackerAgent Paketi ──${N}"
check_python "import hackeragent" "hackeragent Python paketi"
check_python "from hackeragent.core.orchestrator import Orchestrator" "Orchestrator import"
check_python "import mcp" "MCP SDK"
check_tool hackeragent

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

echo -e "${Y}── Python Kütüphaneleri ──${N}"
check_python "import pwn" "pwntools"
check_python "import networkx" "networkx"
check_python "import chromadb" "chromadb"

echo -e "${Y}── Wordlist'ler ──${N}"
check_file "/usr/share/wordlists/rockyou.txt" "rockyou.txt"
check_file "/usr/share/seclists" "seclists"

echo -e "${Y}── HackerAgent Dosyaları ──${N}"
check_file "$REPO_DIR/system_prompt.md" "system_prompt.md"
check_file "$REPO_DIR/config.yaml" "config.yaml"
check_file "$REPO_DIR/.env" ".env"
check_file "$HACKERAGENT_HOME" "Veri dizini ($HACKERAGENT_HOME)"
check_file "$HACKERAGENT_HOME/approvals" "Approval dizini"
check_file "$REPO_DIR/rules/safety-rules.md" "Safety Rules"
check_file "$REPO_DIR/rules/scope-guard.md" "Scope Guard"
check_file "$REPO_DIR/mcp-servers/mcp-kali-tools/server.py" "MCP: kali-tools"
check_file "$REPO_DIR/mcp-servers/mcp-ctf-platform/server.py" "MCP: ctf-platform"
check_file "$REPO_DIR/mcp-servers/mcp-memory-server/server.py" "MCP: memory-server"
check_file "$REPO_DIR/mcp-servers/mcp-telemetry/server.py" "MCP: telemetry"
check_file "$REPO_DIR/mcp-servers/mcp-rag-engine/server.py" "MCP: rag-engine"

echo ""
echo -e "${B}════════════════════════════════════${N}"
echo -e "  ${G}Başarılı: $PASS${N}  |  ${R}Başarısız: $FAIL${N}"
echo -e "${B}════════════════════════════════════${N}"

echo ""
echo -e "${R}╔══════════════════════════════════════════════╗${N}"
echo -e "${R}║                                              ║${N}"
echo -e "${R}║   🔴 HackerAgent v3.0 KURULUM TAMAMLANDI!   ║${N}"
echo -e "${R}║                                              ║${N}"
echo -e "${R}╚══════════════════════════════════════════════╝${N}"
echo ""
echo -e "${Y}Kullanım:${N}"
echo -e "  ${B}cd $REPO_DIR${N}"
echo -e "  ${B}hackeragent${N}                  ${C}# İnteraktif REPL${N}"
echo -e "  ${B}hackeragent --task \"...\"${N}    ${C}# Tek görev${N}"
echo -e "  ${B}hackeragent --list-tools${N}     ${C}# MCP araçlarını listele${N}"
echo -e ""
echo -e "${Y}İlk komutlarınız:${N}"
echo -e "  ${C}→ \"10.10.10.10 hedefini tara\"${N}"
echo -e "  ${C}→ \"Bu CTF challenge'ını çöz\"${N}"
echo -e "  ${C}→ \"example.com üzerinde bug bounty yap\"${N}"
echo ""
echo -e "${Y}Konfigürasyon:${N}"
echo -e "  ${C}$REPO_DIR/.env${N}               ${C}# API key'ler${N}"
echo -e "  ${C}$REPO_DIR/config.yaml${N}        ${C}# Model + MCP server ayarları${N}"
echo -e "  ${C}$HACKERAGENT_HOME/${N}           ${C}# Veri dizini (DB, loglar, RAG)${N}"
echo ""
echo -e "${R}⚠️  Sadece yetkili hedefler üzerinde kullanın!${N}"
echo ""
