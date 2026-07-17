# Stripe — immer nur ineedit.com.co

**DAUERHAFT. IMMER. ÜBERALL.**

| Feld | Wert |
|------|------|
| Shop / Brand | **https://ineedit.com.co** |
| Stripe Account | `acct_1Tg1U0RJECiV6vSm` |
| Login | bullpowersrtkennels@gmail.com |
| Live Secret | `sk_live_51Tg1U…` |
| Business URL in Stripe | https://ineedit.com.co/de |
| Thank-you | https://ineedit.com.co/pages/danke |

## Verboten
- AIITEC `acct_1Swso…` / `sk_live_51Swso…` / `sk_test_51Swso…`
- Jedes andere Stripe-Konto

## Code
```python
from modules.stripe_key_resolver import enforce_ineedit_only, get_working_stripe_key, assert_ineedit_only
enforce_ineedit_only()
key = get_working_stripe_key()  # only ineedit.com.co
```

Startup: `dashboard/server.py` ruft `enforce_ineedit_only()` auf.
HttpGuard rewrites falsche Bearer-Keys auf ineedit.
Self-check: `python3 -c "from modules.stripe_key_resolver import self_check; print(self_check())"`
