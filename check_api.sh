#!/bin/bash
# ═══════════════════════════════════════════════════════════
# API KEY VALIDATOR — Immer vor .env-Eintrag ausführen
# Usage: ./check_api.sh <SERVICE> <KEY>
# Beispiel: ./check_api.sh shopify shpat_abc123
#           ./check_api.sh openai sk-proj-abc
#           ./check_api.sh all   (testet alles aus .env)
# ═══════════════════════════════════════════════════════════

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✅ $1${NC}"; }
fail() { echo -e "${RED}❌ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }

check_http() {
  local name="$1" url="$2" expected="$3"
  shift 3
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$@" "$url" 2>/dev/null)
  if [ "$code" = "$expected" ]; then
    ok "$name → HTTP $code"
    return 0
  elif [ "$code" = "000" ]; then
    fail "$name → Verbindung fehlgeschlagen (Timeout/Down)"
    return 1
  else
    fail "$name → HTTP $code (erwartet $expected)"
    return 1
  fi
}

test_openai() {
  local key="${1:-$OPENAI_API_KEY}"
  check_http "OpenAI" "https://api.openai.com/v1/models" "200" \
    -H "Authorization: Bearer $key"
}

test_anthropic() {
  local key="${1:-$ANTHROPIC_API_KEY}"
  check_http "Anthropic" "https://api.anthropic.com/v1/models" "200" \
    -H "x-api-key: $key" -H "anthropic-version: 2023-06-01"
}

test_perplexity() {
  local key="${1:-$PERPLEXITY_API_KEY}"
  local resp
  resp=$(curl -s --max-time 10 \
    -H "Authorization: Bearer $key" \
    -H "Content-Type: application/json" \
    "https://api.perplexity.ai/chat/completions" \
    -X POST -d '{"model":"sonar","messages":[{"role":"user","content":"hi"}]}' 2>/dev/null)
  if echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if 'choices' in d else 1)" 2>/dev/null; then
    ok "Perplexity → model=sonar OK"
  else
    local err; err=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error',{}).get('type','?'))" 2>/dev/null)
    fail "Perplexity → $err"
  fi
}

test_github() {
  local key="${1:-$GITHUB_TOKEN}"
  check_http "GitHub" "https://api.github.com/user" "200" \
    -H "Authorization: Bearer $key"
}

test_shopify() {
  local token="${1:-$SHOPIFY_ACCESS_TOKEN}"
  local domain="${2:-$SHOPIFY_SHOP_DOMAIN}"
  if [ -z "$domain" ]; then domain="${SHOPIFY_SHOP:-autopilot-store-suite-fmbka}.myshopify.com"; fi
  check_http "Shopify ($domain)" \
    "https://${domain}/admin/api/2024-01/shop.json" "200" \
    -H "X-Shopify-Access-Token: $token"
}

test_supabase() {
  local url="${1:-$SUPABASE_URL}" key="${2:-$SUPABASE_ANON_KEY}"
  check_http "Supabase" "${url}/auth/v1/health" "200" \
    -H "apikey: $key"
}

test_mailchimp() {
  local key="${1:-$MAILCHIMP_API_KEY}"
  local server; server=$(echo "$key" | cut -d'-' -f2)
  check_http "Mailchimp" "https://${server}.api.mailchimp.com/3.0/ping" "200" \
    -u "anystring:$key"
}

test_printify() {
  local key="${1:-$PRINTIFY_TOKEN}"
  check_http "Printify" "https://api.printify.com/v1/shops.json" "200" \
    -H "Authorization: Bearer $key"
}

test_gumroad() {
  local key="${1:-$GUMROAD_TOKEN}"
  check_http "Gumroad" "https://api.gumroad.com/v2/products" "200" \
    -H "Authorization: Bearer $key"
}

test_klaviyo() {
  local key="${1:-$KLAVIYO_PUBLIC_KEY}"
  check_http "Klaviyo" "https://a.klaviyo.com/api/accounts/" "200" \
    -H "Authorization: Klaviyo-API-Key $key" \
    -H "revision: 2024-10-15"
}

test_windsor() {
  local key="${1:-$WINDSOR_API_KEY}"
  check_http "Windsor.ai" \
    "https://connectors.windsor.ai/all?api_key=${key}&date_preset=last_7d&fields=source,clicks&_limit=1" "200"
}

test_gemini() {
  local key="${1:-$GEMINI_API_KEY}"
  if [ -z "$key" ] || [ "$key" = "placeholder_for_testing" ]; then
    warn "Gemini → kein Key gesetzt"
    return 1
  fi
  check_http "Gemini" \
    "https://generativelanguage.googleapis.com/v1beta/models?key=${key}" "200"
}

test_tailscale() {
  local key="${1:-$TAILSCALE_API_KEY}"
  if [ -z "$key" ]; then
    warn "Tailscale → kein Key gesetzt"
    return 1
  fi
  check_http "Tailscale" "https://api.tailscale.com/api/v2/tailnet/-/devices" "200" \
    -u "${key}:"
}

test_ngrok() {
  local key="${1:-$NGROK_API_KEY}"
  if [ -z "$key" ]; then
    warn "ngrok API Key → nicht gesetzt (authtoken ≠ api key)"
    return 1
  fi
  check_http "ngrok" "https://api.ngrok.com/credentials" "200" \
    -H "Authorization: Bearer $key" -H "Ngrok-Version: 2"
}

test_digistore24() {
  local key="${1:-$DIGISTORE24_API_KEY}"
  if [ -z "$key" ]; then
    warn "Digistore24 → kein Key gesetzt"
    return 1
  fi
  # Format: APIID-APISECRET
  local id; id=$(echo "$key" | cut -d'-' -f1)
  local secret; secret=$(echo "$key" | cut -d'-' -f2-)
  check_http "Digistore24" \
    "https://www.digistore24.com/api/call/en/${id}/${secret}/checkConnection" "200"
}

# ── Single-key mode ─────────────────────────────────────────
SERVICE="${1:-all}"
KEY="$2"

case "$SERVICE" in
  openai)     test_openai "$KEY" ;;
  anthropic)  test_anthropic "$KEY" ;;
  perplexity) test_perplexity "$KEY" ;;
  github)     test_github "$KEY" ;;
  shopify)    test_shopify "$KEY" "$3" ;;
  supabase)   test_supabase "$KEY" "$3" ;;
  mailchimp)  test_mailchimp "$KEY" ;;
  printify)   test_printify "$KEY" ;;
  gumroad)    test_gumroad "$KEY" ;;
  klaviyo)    test_klaviyo "$KEY" ;;
  windsor)    test_windsor "$KEY" ;;
  gemini)     test_gemini "$KEY" ;;
  tailscale)  test_tailscale "$KEY" ;;
  ngrok)      test_ngrok "$KEY" ;;
  digistore24) test_digistore24 "$KEY" ;;

  all)
    echo "═══════════════════════════════════════"
    echo "  API KEY VALIDATOR — alle Services"
    echo "═══════════════════════════════════════"
    # Lade .env (portabel über ENV oder Fallback)
    ENV_FILE="${SUPERMEGABOT_ENV:-$HOME/supermegabot/.env}"
    if [ -f "$ENV_FILE" ]; then
      set -a; source "$ENV_FILE" 2>/dev/null; set +a
    elif [ -f "$HOME/.env" ]; then
      set -a; source "$HOME/.env" 2>/dev/null; set +a
    fi
    test_openai
    test_anthropic
    test_perplexity
    test_github
    test_shopify
    test_supabase
    test_mailchimp
    test_printify
    test_gumroad
    test_klaviyo
    test_windsor
    test_gemini
    test_tailscale
    test_ngrok
    test_digistore24
    echo "═══════════════════════════════════════"
    ;;
  *)
    echo "Usage: $0 <service> [key] [extra]"
    echo "Services: openai anthropic perplexity github shopify supabase"
    echo "          mailchimp printify gumroad klaviyo windsor gemini"
    echo "          tailscale ngrok digistore24 all"
    ;;
esac
