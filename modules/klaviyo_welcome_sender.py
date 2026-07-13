"""
Klaviyo Welcome Sender — Sendet Welcome-Email an neue List-Subscriber
Läuft stündlich, trackt bereits begrüßte Subscriber in lokalem State
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import aiohttp

log = logging.getLogger("KlaviyoWelcome")

KLAVIYO_KEY   = os.getenv("KLAVIYO_API_KEY", "")
LIST_ID       = os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")
FROM_EMAIL    = os.getenv("KLAVIYO_FROM_EMAIL", "bullpowersrtkennels@gmail.com")
FROM_LABEL    = "I Need It — Online Shop"
DISCOUNT_CODE = "WILLKOMMEN10"
SHOP_URL      = f"https://{os.getenv('SHOPIFY_SHOP_DOMAIN','ineedit.com.co')}"

DATA_DIR      = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
STATE_FILE    = DATA_DIR / "klaviyo_welcomed.json"

WELCOME_HTML  = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0a0a0a;font-family:Arial,Helvetica,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#0a0a0a">
<tr><td align="center" style="padding:40px 20px">
<table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%">

<!-- Header -->
<tr><td align="center" style="padding-bottom:32px">
  <span style="color:#4ade80;font-size:32px;font-weight:800;letter-spacing:-1px">I Need It ✓</span>
</td></tr>

<!-- Main Card -->
<tr><td style="background:#111;border-radius:16px;padding:40px 36px;border:1px solid #222">
  <p style="color:#888;font-size:13px;text-transform:uppercase;letter-spacing:0.1em;margin:0 0 12px">
    Willkommen bei uns 👋
  </p>
  <h1 style="color:#fff;font-size:26px;font-weight:700;margin:0 0 20px;line-height:1.3">
    Dein Willkommens-Rabatt wartet!
  </h1>
  <p style="color:#aaa;font-size:15px;line-height:1.7;margin:0 0 28px">
    Schön, dass du dabei bist! Als neues Mitglied unserer Community erhältst du
    <strong style="color:#4ade80">10% Rabatt</strong> auf deine erste Bestellung.
    Nutze diesen Code beim Checkout:
  </p>

  <!-- Code Box -->
  <div style="text-align:center;margin:0 0 32px">
    <div style="display:inline-block;background:#0a0a0a;border:2px dashed #4ade80;border-radius:10px;padding:18px 36px">
      <p style="color:#666;font-size:11px;text-transform:uppercase;letter-spacing:0.12em;margin:0 0 6px">Dein Rabattcode</p>
      <p style="color:#4ade80;font-size:28px;font-weight:800;letter-spacing:0.15em;margin:0;font-family:monospace">{DISCOUNT_CODE}</p>
    </div>
  </div>

  <!-- CTA -->
  <div style="text-align:center;margin:0 0 28px">
    <a href="{SHOP_URL}?utm_source=email&utm_medium=welcome&utm_campaign=willkommen10"
       style="display:inline-block;background:#4ade80;color:#000;text-decoration:none;
              padding:16px 40px;border-radius:8px;font-weight:700;font-size:16px;letter-spacing:0.05em">
      Jetzt einkaufen →
    </a>
  </div>

  <p style="color:#555;font-size:13px;line-height:1.6;margin:0">
    Der Code ist einmalig verwendbar und gilt auf alle Produkte im Shop.
    Kein Mindesteinkaufswert notwendig.
  </p>
</td></tr>

<!-- Footer -->
<tr><td align="center" style="padding-top:28px">
  <p style="color:#333;font-size:12px;margin:0">
    Fragen? Schreib uns: {FROM_EMAIL}<br>
    <a href="{{{{ unsubscribe_link }}}}" style="color:#444">Abmelden</a>
  </p>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def _load_welcomed() -> set:
    try:
        data = json.loads(STATE_FILE.read_text())
        return set(data.get("ids", []))
    except Exception:
        return set()


def _save_welcomed(ids: set) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"ids": list(ids), "updated": datetime.utcnow().isoformat()}))


async def fetch_new_subscribers(hours: int = 2) -> list:
    """Holt Subscriber aus den letzten `hours` Stunden."""
    if not KLAVIYO_KEY:
        return []
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")
    h = {"Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}", "revision": "2024-10-15"}
    profiles = []
    async with aiohttp.ClientSession() as s:
        try:
            url = f"https://a.klaviyo.com/api/lists/{LIST_ID}/profiles/"
            params = {"fields[profile]": "id,email,created", "page[size]": "100"}
            async with s.get(url, headers=h, params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    log.warning("Klaviyo profiles fetch: %s", r.status)
                    return []
                d = await r.json(content_type=None)
                for p in d.get("data", []):
                    created = p.get("attributes", {}).get("created", "")
                    if created >= since:
                        email = p.get("attributes", {}).get("email", "")
                        pid   = p.get("id", "")
                        if email and pid:
                            profiles.append({"id": pid, "email": email})
        except Exception as e:
            log.warning("fetch_new_subscribers: %s", e)
    return profiles


async def send_welcome_email(email: str) -> bool:
    """Sendet Welcome-Email via Klaviyo Transactional API."""
    if not KLAVIYO_KEY:
        return False
    h = {"Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}", "revision": "2024-10-15", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as s:
        try:
            # Campaign erstellen
            camp_payload = {"data": {"type": "campaign", "attributes": {
                "name": f"Welcome — {email[:30]} {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                "channel": "email",
                "audiences": {"included": [LIST_ID]},
                "send_options": {"use_smart_sending": False},
                "tracking_options": {"is_tracking_clicks": True, "is_tracking_opens": True},
                "send_strategy": {"method": "immediate"},
            }}}
            async with s.post("https://a.klaviyo.com/api/campaigns/", headers=h, json=camp_payload,
                             timeout=aiohttp.ClientTimeout(total=15)) as r:
                d = await r.json(content_type=None)
                camp_id = d.get("data", {}).get("id", "")
            if not camp_id:
                log.warning("Welcome campaign create failed")
                return False

            await asyncio.sleep(1)

            # Message setzen
            msg_payload = {"data": {"type": "campaign-message", "attributes": {
                "channel": "email",
                "content": {
                    "subject": f"🎉 Dein 10%-Gutschein: {DISCOUNT_CODE}",
                    "preview_text": f"Spare 10% auf deine erste Bestellung — Code: {DISCOUNT_CODE}",
                    "from_email": FROM_EMAIL,
                    "from_label": FROM_LABEL,
                    "body": WELCOME_HTML,
                },
            }, "relationships": {"campaign": {"data": {"type": "campaign", "id": camp_id}}}}}
            async with s.post("https://a.klaviyo.com/api/campaign-messages/", headers=h, json=msg_payload,
                             timeout=aiohttp.ClientTimeout(total=15)) as r2:
                md = await r2.json(content_type=None)
                if not md.get("data", {}).get("id"):
                    return False

            await asyncio.sleep(1)

            # Senden
            async with s.post("https://a.klaviyo.com/api/campaign-send-jobs/", headers=h,
                             json={"data": {"type": "campaign-send-job", "id": camp_id}},
                             timeout=aiohttp.ClientTimeout(total=15)) as r3:
                ok = r3.status in (200, 201, 202)
                if ok:
                    log.info("Welcome email sent to %s (campaign %s)", email, camp_id)
                return ok
        except Exception as e:
            log.warning("send_welcome_email to %s: %s", email, e)
            return False


async def run_welcome_batch() -> dict:
    """Holt neue Subscriber und sendet Welcome-Emails an unbekannte."""
    welcomed = _load_welcomed()
    new_subs = await fetch_new_subscribers(hours=2)
    sent = 0
    skipped = 0
    for sub in new_subs:
        pid = sub["id"]
        if pid in welcomed:
            skipped += 1
            continue
        ok = await send_welcome_email(sub["email"])
        if ok:
            welcomed.add(pid)
            sent += 1
        await asyncio.sleep(2)
    _save_welcomed(welcomed)
    return {"new_found": len(new_subs), "welcomed": sent, "skipped": skipped}
