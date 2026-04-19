#!/bin/bash
# ============================================================
# Flag Cracker — OpenRouter Tek Key Kurulum Scripti (v3)
# Claude Code + Qwen + Hermes tek OpenRouter key ile çalışır.
# ============================================================

set -e

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  🔑 Flag Cracker — OpenRouter API Kurulumu (v3)         ║"
echo "║  Claude Code + Qwen + Hermes tek key ile çalışacak      ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── ADIM 1: API Key Al ──
echo "[1/4] OpenRouter API Key giriniz"
echo "      (https://openrouter.ai/keys adresinden alabilirsiniz)"
echo ""
read -sp "API Key: " OPENROUTER_KEY
echo ""

if [ -z "$OPENROUTER_KEY" ]; then
    echo "❌ API key boş olamaz!"
    exit 1
fi

# ── ADIM 2: API Key'i Test Et ──
echo ""
echo "[2/4] API Key test ediliyor..."

TEST_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST https://openrouter.ai/api/v1/chat/completions \
    -H "Authorization: Bearer $OPENROUTER_KEY" \
    -H "Content-Type: application/json" \
    -d '{
        "model": "qwen/qwen3.6-plus",
        "messages": [{"role": "user", "content": "Say OK"}],
        "max_tokens": 5
    }' 2>/dev/null)

HTTP_CODE=$(echo "$TEST_RESPONSE" | tail -1)

if [ "$HTTP_CODE" == "200" ]; then
    echo "✅ API Key geçerli! qwen/qwen3.6-plus modeli erişilebilir."
elif [ "$HTTP_CODE" == "401" ]; then
    echo "❌ HATA: 401 — API Key geçersiz veya hesap bulunamadı!"
    exit 1
elif [ "$HTTP_CODE" == "402" ]; then
    echo "⚠️  UYARI: 402 — Yetersiz bakiye."
    read -p "Yine de devam? (e/h): " confirm
    [ "$confirm" != "e" ] && exit 1
else
    echo "⚠️  HTTP $HTTP_CODE yanıtı! OpenRouter sunucularında yoğunluk olabilir..."
fi

# ── ADIM 3: Ortam Değişkenlerini Ayarla ──
echo ""
echo "[3/4] Ortam değişkenleri ayarlanıyor..."

# Eski ayarları temizle
sed -i '/# --- Flag Cracker OpenRouter ---/,/# --- End Flag Cracker ---/d' ~/.bashrc 2>/dev/null || true

# Yeni ayarları ekle
cat >> ~/.bashrc << ENVBLOCK

# --- Flag Cracker OpenRouter ---
export OPENROUTER_API_KEY="$OPENROUTER_KEY"
export ANTHROPIC_API_KEY="$OPENROUTER_KEY"
export ANTHROPIC_BASE_URL="https://openrouter.ai/api/v1"
export CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS="true"
unset ANTHROPIC_AUTH_TOKEN
# --- End Flag Cracker ---
ENVBLOCK

echo "✅ .bashrc güncellendi"

# ── ADIM 4: settings.json güncelle ──
echo ""
echo "[4/4] settings.json güncelleniyor..."

PROJECT_SETTINGS="$(dirname "$0")/.claude/settings.json"
HOME_SETTINGS="$HOME/.claude/settings.json"

for SETTINGS_FILE in "$PROJECT_SETTINGS" "$HOME_SETTINGS"; do
    if [ -f "$SETTINGS_FILE" ]; then
        python3 -c "
import json
with open('$SETTINGS_FILE', 'r') as f:
    data = json.load(f)
data['openrouter_api_key'] = '$OPENROUTER_KEY'
with open('$SETTINGS_FILE', 'w') as f:
    json.dump(data, f, indent=2)
print('✅ $SETTINGS_FILE güncellendi')
" 2>/dev/null || echo "⚠️  $SETTINGS_FILE güncellenemedi"
    fi
done

# ── SONUÇ ──
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ✅ KURULUM TAMAMLANDI!                                 ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║                                                          ║"
echo "║  Ayarlanan değişkenler:                                  ║"
echo "║  • OPENROUTER_API_KEY  → Qwen/Hermes tool'ları         ║"
echo "║  • ANTHROPIC_API_KEY   → Claude Code (OpenRouter Key)   ║"
echo "║  • ANTHROPIC_BASE_URL  → openrouter.ai/api/v1           ║"
echo "║                                                          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "🚀 Şimdi şu komutları sırayla çalıştırın:"
echo ""
echo "   source ~/.bashrc"
echo "   claude --model qwen/qwen3.6-plus"
echo ""
