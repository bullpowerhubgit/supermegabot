---
name: ai-budget
description: AI Credit-Schutz — Budget-Limits, Whitelist und Provider-Fallback für SuperMegaBot
paths:
  - "modules/ai_budget_guard.py"
  - "modules/ai_client.py"
---

## PFLICHT-REGEL: NIEMALS direkt Anthropic importieren!

**Alle neuen Module die KI nutzen → IMMER über `ai_client.ai_complete()`** — nie direkt Anthropic SDK.

```python
from modules.ai_client import ai_complete
result = await ai_complete(prompt="...", model="claude-3-haiku")
```

## Budget-Limits (`modules/ai_budget_guard.py` + Railway Env Vars)

| Variable | Default |
|----------|---------|
| `ANTHROPIC_DAILY_USD_LIMIT` | 0.30 |
| `ANTHROPIC_HOURLY_USD_LIMIT` | 0.05 |
| `OPENAI_DAILY_USD_LIMIT` | 0.30 |
| `OPENAI_HOURLY_USD_LIMIT` | 0.05 |
| `PERPLEXITY_DAILY_USD_LIMIT` | 0.10 |
| `PERPLEXITY_HOURLY_USD_LIMIT` | 0.03 |
| `GLOBAL_AI_DAILY_USD_CAP` | 0.70 |

## Budget-Whitelist

Nur Module in `_AI_ALLOWED_WHITELIST` (in `ai_budget_guard.py`) dürfen KI nutzen:
Shopify-Income, Stripe-Billing, Digistore24, Gumroad, Klaviyo-Email, Meta-Ads, Revenue-Report u.a.

## Provider-Fallback-Reihenfolge (`modules/ai_client.py`)

1. OpenClaw (lokal / gratis)
2. Groq (gratis-Tier)
3. DeepSeek
4. **OpenRouter** (Haupt-Fallback wenn Anthropic-Quota leer — `OPENROUTER_API_KEY` in Railway)
5. Anthropic Claude

→ Bei Anthropic-Quota-Limit übernimmt OpenRouter automatisch. Bei jedem Railway-Deploy: `GROQ_API_KEY` + `OPENROUTER_API_KEY` prüfen.

## Watchdogs

- `free_api_hunter`: alle 12h neue kostenlose API-Keys suchen
- `api_hunt_watchdog`: alle 1h prüfen ob Provider erreichbar
