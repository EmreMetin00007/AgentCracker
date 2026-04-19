#!/bin/bash
# ============================================================
# Flag Cracker — OpenRouter Tek Key Kurulum Scripti
# Tüm LLM'leri (Claude Code + Qwen + Hermes) tek OpenRouter
# API key ile çalıştırır.
# ============================================================

set -e

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  🔑 Flag Cracker — OpenRouter API Kurulumu              ║"
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

# Key formatı kontrolü
if [[ ! "$OPENROUTER_KEY" == sk-or-* ]]; then
    echo "⚠️  Uyarı: Key 'sk-or-' ile başlamıyor. Doğru key olduğundan emin olun."
    read -p "Devam etmek istiyor musunuz? (e/h): " confirm
    if [ "$confirm" != "e" ]; then
        exit 1
    fi
fi

# ── ADIM 2: API Key'i Test Et ──
echo ""
echo "[2/4] API Key test ediliyor..."

TEST_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST https://openrouter.ai/api/v1/chat/completions \
    -H "Authorization: Bearer $OPENROUTER_KEY" \
    -H "Content-Type: application/json" \
    -d '{
        "model": "qwen/qwen-2.5-72b-instruct",
        "messages": [{"role": "user", "content": "Say OK"}],
        "max_tokens": 5
    }' 2>/dev/null)

HTTP_CODE=$(echo "$TEST_RESPONSE" | tail -1)
BODY=$(echo "$TEST_RESPONSE" | head -n -1)

if [ "$HTTP_CODE" == "200" ]; then
    echo "✅ API Key geçerli! Bağlantı başarılı."
elif [ "$HTTP_CODE" == "401" ]; then
    echo "❌ HATA: 401 — API Key geçersiz veya hesap bulunamadı!"
    echo "   → https://openrouter.ai/keys adresinden yeni key oluşturun"
    echo "   Detay: $BODY"
    exit 1
elif [ "$HTTP_CODE" == "402" ]; then
    echo "⚠️  UYARI: 402 — Yetersiz bakiye. OpenRouter hesabınıza kredi ekleyin."
    echo "   → https://openrouter.ai/credits"
    read -p "Yine de devam etmek istiyor musunuz? (e/h): " confirm
    if [ "$confirm" != "e" ]; then
        exit 1
    fi
else
    echo "⚠️  Beklenmeyen yanıt (HTTP $HTTP_CODE). Devam ediliyor..."
    echo "   Detay: $BODY"
fi

# ── ADIM 3: Ortam Değişkenlerini Ayarla ──
echo ""
echo "[3/4] Ortam değişkenleri ayarlanıyor..."

# Mevcut .bashrc'den eski ayarları temizle
sed -i '/# --- Flag Cracker OpenRouter ---/,/# --- End Flag Cracker ---/d' ~/.bashrc 2>/dev/null || true
sed -i '/OPENROUTER_API_KEY/d' ~/.bashrc 2>/dev/null || true
sed -i '/ANTHROPIC_BASE_URL.*openrouter/d' ~/.bashrc 2>/dev/null || true
sed -i '/ANTHROPIC_API_KEY.*sk-or/d' ~/.bashrc 2>/dev/null || true

# Yeni ayarları ekle
cat >> ~/.bashrc << 'ENVBLOCK'

# --- Flag Cracker OpenRouter ---
# Claude Code → OpenRouter üzerinden çalışır
ENVBLOCK

echo "export OPENROUTER_API_KEY=\"$OPENROUTER_KEY\"" >> ~/.bashrc
echo "export ANTHROPIC_API_KEY=\"$OPENROUTER_KEY\"" >> ~/.bashrc
echo 'export ANTHROPIC_BASE_URL="https://openrouter.ai/api/v1"' >> ~/.bashrc

cat >> ~/.bashrc << 'ENVBLOCK2'
# --- End Flag Cracker ---
ENVBLOCK2

# Mevcut shell'e de uygula
export OPENROUTER_API_KEY="$OPENROUTER_KEY"
export ANTHROPIC_API_KEY="$OPENROUTER_KEY"
export ANTHROPIC_BASE_URL="https://openrouter.ai/api/v1"

echo "✅ .bashrc güncellendi"

# ── ADIM 4: settings.json güncelle ──
echo ""
echo "[4/4] settings.json güncelleniyor..."

SETTINGS_FILE="$HOME/.claude/settings.json"
PROJECT_SETTINGS="$(dirname "$0")/.claude/settings.json"

# Proje settings.json'ı güncelle
if [ -f "$PROJECT_SETTINGS" ]; then
    # Python ile JSON güncelle (jq yoksa diye)
    python3 -c "
import json
with open('$PROJECT_SETTINGS', 'r') as f:
    data = json.load(f)
data['openrouter_api_key'] = '$OPENROUTER_KEY'
with open('$PROJECT_SETTINGS', 'w') as f:
    json.dump(data, f, indent=2)
print('✅ Proje settings.json güncellendi')
" 2>/dev/null || echo "⚠️  Proje settings.json güncellenemedi (manuel düzenleyin)"
fi

# Home dizini settings.json
if [ -f "$SETTINGS_FILE" ]; then
    python3 -c "
import json
with open('$SETTINGS_FILE', 'r') as f:
    data = json.load(f)
data['openrouter_api_key'] = '$OPENROUTER_KEY'
with open('$SETTINGS_FILE', 'w') as f:
    json.dump(data, f, indent=2)
print('✅ ~/.claude/settings.json güncellendi')
" 2>/dev/null || echo "⚠️  ~/.claude/settings.json güncellenemedi"
fi

# ── SONUÇ ──
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ✅ KURULUM TAMAMLANDI!                                 ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║                                                          ║"
echo "║  Ayarlanan değişkenler:                                  ║"
echo "║  • OPENROUTER_API_KEY  → Qwen + Hermes tool'ları        ║"
echo "║  • ANTHROPIC_API_KEY   → Claude Code (OpenRouter proxy)  ║"
echo "║  • ANTHROPIC_BASE_URL  → openrouter.ai/api/v1           ║"
echo "║                                                          ║"
echo "║  Kullanılabilir modeller:                                ║"
echo "║  • anthropic/claude-sonnet-4-20250514 (ücretli)          ║"
echo "║  • qwen/qwen-2.5-72b-instruct (ucuz/ücretsiz)           ║"
echo "║  • nousresearch/hermes-3-llama-3.1-405b                  ║"
echo "║                                                          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "🚀 Şimdi Claude Code'u şu şekilde başlatın:"
echo ""
echo "   # Claude modeli ile (ücretli ama en iyi):"
echo "   claude --model anthropic/claude-sonnet-4-20250514"
echo ""
echo "   # Veya ücretsiz/ucuz model ile:"
echo "   claude --model qwen/qwen-2.5-72b-instruct"
echo ""
echo "   # Yeni terminal açtıysanız önce:"
echo "   source ~/.bashrc"
echo ""
