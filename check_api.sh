#!/bin/bash

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
BLUE="\033[0;34m"
RESET="\033[0m"

ok() { echo -e "${GREEN}✓${RESET} $1"; }
warn() { echo -e "${YELLOW}⚠${RESET} $1"; }
info() { echo -e "${BLUE}→${RESET} $1"; }
fail() { echo -e "${RED}✗${RESET} $1"; }

DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICES=(openai anthropic perplexity github shopify supabase mailchimp printify gumroad klaviyo windsor gemini tailscale ngrok digistore24)

trim() {
    local value="$1"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    printf '%s' "$value"
}

first_non_empty() {
    local value
    for value in "$@"; do
        value="$(trim "$value")"
        if [ -n "$value" ]; then
            printf '%s' "$value"
            return 0
        fi
    done
    return 1
}

require_values() {
    local service="$1"
    shift
    local missing=()
    local label value

    while [ "$#" -ge 2 ]; do
        label="$1"
        value="$(trim "$2")"
        shift 2
        if [ -z "$value" ]; then
            missing+=("$label")
        fi
    done

    if [ "${#missing[@]}" -gt 0 ]; then
        local joined="${missing[0]}"
        local item
        for item in "${missing[@]:1}"; do
            joined="$joined, $item"
        done
        warn "$service → fehlt: $joined"
        return 1
    fi

    return 0
}

load_env() {
    local env_file="$DIR/.env"
    if [ -f "$env_file" ]; then
        set -a
        # shellcheck disable=SC1090
        . "$env_file"
        set +a
    fi
}

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
    require_values "OpenAI" "OPENAI_API_KEY" "$key" || return 1
    check_http "OpenAI" "https://api.openai.com/v1/models" "200" \
        -H "Authorization: Bearer $key"
}

test_anthropic() {
    local key="${1:-$ANTHROPIC_API_KEY}"
    require_values "Anthropic" "ANTHROPIC_API_KEY" "$key" || return 1
    check_http "Anthropic" "https://api.anthropic.com/v1/models" "200" \
        -H "x-api-key: $key" -H "anthropic-version: 2023-06-01"
}

test_perplexity() {
    local key="${1:-$PERPLEXITY_API_KEY}"
    require_values "Perplexity" "PERPLEXITY_API_KEY" "$key" || return 1
    check_http "Perplexity" "https://api.perplexity.ai/chat/completions" "200" \
        -X POST \
        -H "Authorization: Bearer $key" \
        -H "Content-Type: application/json" \
        -d '{"model":"sonar","messages":[{"role":"user","content":"ping"}],"max_tokens":1}'
}

test_github() {
    local key="${1:-$GITHUB_TOKEN}"
    require_values "GitHub" "GITHUB_TOKEN" "$key" || return 1
    check_http "GitHub" "https://api.github.com/user" "200" \
        -H "Authorization: Bearer $key" \
        -H "Accept: application/vnd.github.v3+json"
}

test_shopify() {
    local url="${1:-$(first_non_empty "$SHOPIFY_STORE_URL" "$SHOPIFY_SHOP_URL")}"
    local token="${2:-$(first_non_empty "$SHOPIFY_ACCESS_TOKEN" "$SHOPIFY_ADMIN_API_TOKEN" "$SHOPIFY_SUITE_ACCESS_TOKEN")}"
    if [ -z "$(trim "$token")" ]; then
        warn "Shopify → kein Access Token gesetzt (Konfigurationsproblem)"
        return 1
    fi
    require_values "Shopify" "SHOPIFY_STORE_URL" "$url" || return 1
    check_http "Shopify" "${url%/}/admin/api/2024-10/shop.json" "200" \
        -H "X-Shopify-Access-Token: $token"
}

test_supabase() {
    local url="${1:-$SUPABASE_URL}"
    local key="${2:-$SUPABASE_ANON_KEY}"
    require_values "Supabase" "SUPABASE_URL" "$url" "SUPABASE_ANON_KEY" "$key" || return 1
    check_http "Supabase" "${url%/}/rest/v1/" "200" \
        -H "apikey: $key" \
        -H "Authorization: Bearer $key"
}

test_mailchimp() {
    local key="${1:-$MAILCHIMP_API_KEY}"
    local prefix="${2:-$MAILCHIMP_SERVER_PREFIX}"
    local auth

    if [ -z "$(trim "$prefix")" ] && [[ "$key" == *-* ]]; then
        prefix="${key##*-}"
    fi

    require_values "Mailchimp" "MAILCHIMP_API_KEY" "$key" "MAILCHIMP_SERVER_PREFIX" "$prefix" || return 1
    auth=$(printf 'any:%s' "$key" | base64 | tr -d '\n')
    check_http "Mailchimp" "https://${prefix}.api.mailchimp.com/3.0/ping" "200" \
        -H "Authorization: Basic $auth"
}

test_printify() {
    local key="${1:-$(first_non_empty "$PRINTIFY_TOKEN" "$PRINTIFY_API_TOKEN")}"
    require_values "Printify" "PRINTIFY_TOKEN" "$key" || return 1
    check_http "Printify" "https://api.printify.com/v1/shops.json" "200" \
        -H "Authorization: Bearer $key"
}

test_gumroad() {
    local key="${1:-$(first_non_empty "$GUMROAD_TOKEN" "$GUMROAD_ACCESS_TOKEN")}"
    require_values "Gumroad" "GUMROAD_TOKEN" "$key" || return 1
    check_http "Gumroad" "https://api.gumroad.com/v2/user?access_token=$key" "200"
}

test_klaviyo() {
    local key="${1:-$(first_non_empty "$KLAVIYO_API_KEY" "$KLAVIYO_PUBLIC_KEY")}"
    require_values "Klaviyo" "KLAVIYO_API_KEY" "$key" || return 1
    check_http "Klaviyo" "https://a.klaviyo.com/api/accounts/" "200" \
        -H "Authorization: Klaviyo-API-Key $key" \
        -H "revision: 2024-02-15"
}

test_windsor() {
    local key="${1:-$WINDSOR_API_KEY}"
    require_values "Windsor.ai" "WINDSOR_API_KEY" "$key" || return 1
    check_http "Windsor.ai" "https://connectors.windsor.ai/all?api_key=$key&fields=source&date_from=today" "200"
}

test_gemini() {
    local key="${1:-$GEMINI_API_KEY}"
    require_values "Gemini" "GEMINI_API_KEY" "$key" || return 1
    check_http "Gemini" "https://generativelanguage.googleapis.com/v1beta/models?key=$key" "200"
}

test_tailscale() {
    local key="${1:-$TAILSCALE_API_KEY}"
    local tailnet="${2:-${TAILSCALE_TAILNET:--}}"
    require_values "Tailscale" "TAILSCALE_API_KEY" "$key" || return 1
    check_http "Tailscale" "https://api.tailscale.com/api/v2/tailnet/${tailnet}/devices" "200" \
        -u "$key:"
}

test_ngrok() {
    local key="${1:-$NGROK_API_KEY}"
    require_values "Ngrok" "NGROK_API_KEY" "$key" || return 1
    check_http "Ngrok" "https://api.ngrok.com/reserved_domains" "200" \
        -H "Authorization: Bearer $key" \
        -H "Ngrok-Version: 2"
}

test_digistore24() {
    local key="${1:-$DIGISTORE24_API_KEY}"
    require_values "Digistore24" "DIGISTORE24_API_KEY" "$key" || return 1
    check_http "Digistore24" "https://www.digistore24.com/api/call" "200" \
        -H "X-DS24-API-Key: $key"
}

usage() {
    echo -e "${BOLD}Usage:${RESET} $0 {${SERVICES[*]}|all}"
}

run_service() {
    case "$1" in
        openai) test_openai ;;
        anthropic) test_anthropic ;;
        perplexity) test_perplexity ;;
        github) test_github ;;
        shopify) test_shopify ;;
        supabase) test_supabase ;;
        mailchimp) test_mailchimp ;;
        printify) test_printify ;;
        gumroad) test_gumroad ;;
        klaviyo) test_klaviyo ;;
        windsor) test_windsor ;;
        gemini) test_gemini ;;
        tailscale) test_tailscale ;;
        ngrok) test_ngrok ;;
        digistore24) test_digistore24 ;;
        *) usage; return 1 ;;
    esac
}

main() {
    local mode="${1:-all}"
    local status=0
    local service

    load_env

    if [ "$mode" = "all" ]; then
        for service in "${SERVICES[@]}"; do
            info "Teste $service..."
            if ! run_service "$service"; then
                status=1
            fi
        done
        return "$status"
    fi

    run_service "$mode"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
