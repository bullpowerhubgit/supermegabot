# SuperMegaBot — Current Status
**Stand: 2026-07-16**

## System Health
- Production: ✅ https://supermegabot-production.up.railway.app/health → OK
- Circuits: alle geschlossen (0 offene)
- Tasks: 356 registriert, 2 mit kleinen Fehlerraten (unkritisch)
- Uptime: ~4h (nach letztem Deploy)

## Stripe ✅ VOLLSTÄNDIG EINGERICHTET
- **Aktiver Key**: STRIPE_SECRET_KEY_FULL (sk_live_51Tg1U0...) → bullpowersrtkennels@gmail.com
- **WARNUNG**: STRIPE_SECRET_KEY (aiitec sk_live_51Swso...) ist **ABGELAUFEN** → neuen Key im Stripe-Dashboard erstellen und in Railway setzen
- Subscription Pläne (NEU erstellt auf aktivem Konto):
  - Starter €49/mo: price_1TtfRvRJECiV6vSmX3T1Kjn2 ✅
  - Pro €99/mo: price_1TtfRwRJECiV6vSmbNBlDUzo ✅
  - Enterprise €299/mo: price_1TtfRyRJECiV6vSmwUgvoj0x ✅
  - Telegram Starter €29/mo: price_1TjodoRJECiV6vSmL726jLd3 ✅
  - Telegram Pro €79/mo: price_1TjodoRJECiV6vSmcWkhHtWz ✅
  - Telegram Agency €199/mo: price_1TjodpRJECiV6vSmFVtPj8yb ✅
- Checkout Session: ✅ Getestet — live URL generiert
- Webhook: ✅ we_1TstiR... → /api/stripe/webhook → alle Events aktiv
- Customer Portal: ✅ bpc_1TtFla... aktiv
- stripe_automation.py: STRIPE_SECRET_KEY_FULL hat jetzt Priorität (Fallback-Logik)

## URL-Fix (Posts) ✅
- Alle myshopify.com URLs in Posts → ineedit.com.co ersetzt (44 Dateien)
- DS24 Affiliate Link: 669750 korrekt (war 668035)
- PUBLIC_SHOP_URL default in allen Posting-Modulen gesetzt

## ��️ OFFENE PUNKTE (Railway Variables manuell setzen)
```
railway link  # im supermegabot Verzeichnis ausführen
railway variables set STRIPE_SECRET_KEY=sk_live_51Tg1U0RJECiV6vSm...
railway variables set STRIPE_PRICE_STARTER=price_1TtfRvRJECiV6vSmX3T1Kjn2
railway variables set STRIPE_PRICE_PRO=price_1TtfRwRJECiV6vSmbNBlDUzo
railway variables set STRIPE_PRICE_ENTERPRISE=price_1TtfRyRJECiV6vSmwUgvoj0x
railway variables set STRIPE_PRICE_TELEGRAM_STARTER=price_1TjodoRJECiV6vSmL726jLd3
railway variables set STRIPE_PRICE_TELEGRAM_PRO=price_1TjodoRJECiV6vSmcWkhHtWz
railway variables set STRIPE_PRICE_TELEGRAM_AGENCY=price_1TjodpRJECiV6vSmFVtPj8yb
railway variables set PUBLIC_SHOP_URL=https://ineedit.com.co
```

## Bekannte Probleme
- Gmail Accounts: Tageslimit 80/Account — kein Fehler heute
- Watchdog Port 9003: dashboard-seitiger Proxy → Service nicht nötig (kein claude_watchdog auf 9003)
- DeepSeek 402, Anthropic 400, Perplexity 401: API Credits/Keys erneuern nötig
