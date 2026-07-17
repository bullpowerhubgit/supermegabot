# iCloud Import Report — 2026-07-17 15:31 UTC

## Files processed

| File | Action |
|------|--------|
| `telegram_dm_sheet_30.md` | → `marketing/` + `modules/telegram_dm_sheet.py` |
| `telegram_dm_sheet_30_Version1.md` | → `marketing/` (identical DE/EN sheet) |
| `landingpage_copy_en.md` | → `marketing/` |
| `stripe_products_prices.yml` | → `config/` (€49/€99/€299 + addons + DFY) |
| `env_billing_template.env` | → `config/` (placeholders only, no secrets) |
| `claude_automation.py` | **NOT merged** — iCloud copy lacks budget guard; archived `config/icloud_import/…` |
| `Konto_…Auszug_2026_0007.PDF` | private only `data/private/` (gitignored) |
| `GitHub-Copilot-darwin-arm64.dmg` | left in iCloud (210MB installer) — install manually if needed |

## Stripe catalog from YAML (targets)

| Plan | Amount | Status on Stripe live |
|------|--------|------------------------|
| SuperMegaBot Starter | €49/mo | already exists (buy.stripe.com links in MONETIZE_SCAN) |
| SuperMegaBot Growth | €99/mo | catalog target |
| SuperMegaBot Scale | €299/mo | catalog target |
| Extra Store addon | €19/mo | catalog target |
| AI 1000 addon | €29/mo | catalog target |
| DFY Setup | €299 once | catalog target |
| Premium Onboarding | €149 once | catalog target |

Env billing template only had placeholders (`sk_live_...`) — **no new secrets** to install.

## Bank statement (private summary — no full IBAN in git)

- Account: Sparkasse Landsberg-Dießen private giro, statement 7/2026
- Opening ~€70 → closing **−€5.85** (overdraft interest charged)
- Income: Kindergeld €518, private transfers, Kraken €81.30
- **No SuperMegaBot/Stripe SaaS payout lines** in this month
- Not monetizable as product; cash-flow signal: runway tight → push Stripe traffic

## Next automation hooks

```python
from modules.telegram_dm_sheet import pick, followups
print(pick('de', 3))
```

Landing EN copy ready for Netlify/Vercel landings.
