# AGENT CREDENTIALS SYNC — SANITIZED
# Last updated: 2026-07-11
# =========================================================
# IMPORTANT:
# - No real credentials in this file.
# - Store real values only in Railway environment variables / local .env (gitignored).
# - Any leaked credential must be rotated immediately.
# =========================================================

## Environment Variables (names only)

### AI
- ANTHROPIC_API_KEY
- OPENAI_API_KEY
- DEEPSEEK_API_KEY
- OPENROUTER_API_KEY

### Telegram
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

### Shopify
- SHOPIFY_SHOP_DOMAIN
- SHOPIFY_ACCESS_TOKEN
- SHOPIFY_API_VERSION

### Stripe
- STRIPE_SECRET_KEY
- STRIPE_PRICE_STARTER
- STRIPE_PRICE_PRO
- STRIPE_PRICE_ENTERPRISE

### Supabase
- SUPABASE_URL
- SUPABASE_PROJECT_ID

### Digistore24
- DIGISTORE24_API_KEY
- DIGISTORE24_API_KEY_READONLY

### Mailchimp
- MAILCHIMP_API_KEY
- MAILCHIMP_SERVER_PREFIX
- MAILCHIMP_LIST_ID
- MAILCHIMP_CLIENT_ID
- MAILCHIMP_CLIENT_SECRET

### Klaviyo
- KLAVIYO_API_KEY
- KLAVIYO_LIST_ID

### Twilio
- TWILIO_ACCOUNT_SID
- TWILIO_AUTH_TOKEN
- TWILIO_API_KEY_SID
- TWILIO_API_KEY_SECRET
- TWILIO_FROM_NUMBER

### Google / YouTube
- YOUTUBE_API_KEY
- YOUTUBE_CHANNEL_ID
- GCP_PROJECT_ID
- GCP_REGION
- GOOGLE_API_KEY

### Meta / Facebook / Instagram
- FACEBOOK_BUSINESS_ID
- FACEBOOK_PAGE_ID
- FACEBOOK_ACCESS_TOKEN
- FACEBOOK_PAGE_TOKEN
- FACEBOOK_PAGE_TOKEN_IWIN
- FACEBOOK_PAGE_TOKEN_I_NEED_IT
- FACEBOOK_PAGE_TOKEN_AIITEC
- INSTAGRAM_ID_AIITEC
- INSTAGRAM_USER_AIITEC

### GitHub
- GITHUB_TOKEN
- GITHUB_USER
- REPO

---

## Operational Notes (non-secret)
- DS24 buyer email path: order["buyer"]["email"]
- Klaviyo header format:
  - Authorization: "Klaviyo-API-Key <KEY>"
  - revision: "2024-06-15"
- Facebook Graph API posting: POST /{page_id}/feed with page token
- Scheduler intervals are defined in automation_scheduler.py

---

## Mandatory Security Actions
1. Rotate/revoke all exposed keys immediately.
2. Update Railway env vars with new keys.
3. Remove secrets from git history (git-filter-repo or BFG).
4. Enable secret scanning + push protection.
