---
name: telegram-spam
description: TgGate Interceptor + Scheduler-Blocklist — Telegram-Spam-Schutzregeln für SuperMegaBot
paths:
  - "core/automation_scheduler.py"
  - "modules/tg_gate.py"
  - "modules/viral_window_scanner.py"
---

## TgGate — Globaler Interceptor (`modules/tg_gate.py`)

Patcht `aiohttp.ClientSession.post` und `urllib.urlopen` beim Server-Start.
ALLE sendMessage-Calls laufen durch:
- **Pattern-Filter**: 17 Spam-Patterns (Viral Window Alert, 0 Chancen 0 Imports, MRR €0 etc.)
- **Dedup**: 5-Minuten-Fenster (kein Doppel-Senden)
- **Rate-Limit**: 50/Stunde (`TG_MAX_PER_HOUR` Railway-Env, default 50)

Installiert in `dashboard/server.py` ganz oben in `create_app()`:
```python
from modules.tg_gate import install_global_intercept
install_global_intercept()
```

Stats: `GET /api/tg-gate/stats`

## Scheduler-Blocklist (`core/automation_scheduler.py`)

Folgende Tasks sind in `_POSTING_BLOCKLIST` dauerhaft geblockt:
- `viral_window_scanner` — 72x Garbage-Alerts
- `ebay_arbitrage_scan` — 0-Result-Reports
- `money_machine_run` — 0-Aktivität-Summaries
- `insolvenz_radar_scan` — ungeprüfte B2B-Leads
- `conversion_optimizer` — All-Zeros-Reports
- `bpi_sys13_partner_channel` — DSGVO-kritisch (Cold-Emails!)
- `lead_outreach` / `lead_delivery` — Cold-Outreach verboten
- `buyer_traffic_engine` — Spam
- `viral_score_tracker` / `viral_push` / `viraltrendpush` — Spam
- `posting_engine_run` / `social_post_scheduler` — Spam
- `tiktok_ads_engine` / `tiktok_content_push` — Spam
- `vorsprung_scan` — Spam
- `daily_summary` / `wochenbericht` — Zusammenfassungen ohne Wert
- `rudiclone_daily_brief` — Spam
- `boersenbot_run` — irrelevant
- `lead_finder` / `lead_enricher` — keine Cold-Outreach
- `seo_ranker` / `seo_audit` — kein Wert
- `trend_push_scheduler` / `trendbot_run` — Spam
- 10+ weitere (vollständige Liste in `_POSTING_BLOCKLIST` in der Datei)

### KRITISCHER UNTERSCHIED:
- `_POSTING_BLOCKLIST` → Task wird geblockt ✓
- `_REVENUE_TASKS` → Tasks die NUR im REVENUE_MODE laufen ≠ geblockt!

## Modul-Level Guards
- `viral_window_scanner.py`: `VIRAL_ADMIN_ALERTS=false` (Railway Env, default disabled)
- `ebay_arbitrage.py`: 0-Result Filter → kein Telegram
- `money_machine.py`: Activity-Check → nur senden wenn imports/alerts > 0
- `partner_channel.py`: `PARTNER_ONBOARDING_ENABLED=false` (Railway Env, default disabled)
