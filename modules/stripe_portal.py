"""Stripe Billing Portal — Kunden verwalten ihr Abo selbst"""
import logging
import os
import aiohttp
from aiohttp import web

log = logging.getLogger("StripePortal")

STRIPE_KEY          = os.getenv("STRIPE_SECRET_KEY", "")
PORTAL_CONFIG_ID    = "bpc_1TtFlaRJECiV6vSmVAGz89dV"
BASE_URL            = os.getenv("RAILWAY_STATIC_URL", "https://aiitec-saas-production.up.railway.app")


async def _find_or_create_customer(email: str) -> str:
    """Gibt Stripe Customer ID zurück oder erstellt einen neuen."""
    async with aiohttp.ClientSession() as s:
        # Suchen
        async with s.get(
            f"https://api.stripe.com/v1/customers?email={email}&limit=1",
            headers={"Authorization": f"Bearer {STRIPE_KEY}"},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            data = await r.json()
            customers = data.get("data", [])
            if customers:
                return customers[0]["id"]

        # Neu erstellen
        async with s.post(
            "https://api.stripe.com/v1/customers",
            data={"email": email},
            headers={"Authorization": f"Bearer {STRIPE_KEY}"},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            data = await r.json()
            return data["id"]


async def create_portal_session(email: str) -> str:
    """Erstellt eine Stripe Billing Portal Session und gibt die URL zurück."""
    customer_id = await _find_or_create_customer(email)

    async with aiohttp.ClientSession() as s:
        async with s.post(
            "https://api.stripe.com/v1/billing_portal/sessions",
            data={
                "customer": customer_id,
                "return_url": BASE_URL,
                "configuration": PORTAL_CONFIG_ID,
            },
            headers={"Authorization": f"Bearer {STRIPE_KEY}"},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            data = await r.json()
            url = data.get("url")
            if not url:
                raise RuntimeError(f"Portal Session Fehler: {data}")
            return url


async def handle_portal(req: web.Request) -> web.Response:
    """GET/POST /portal?email=... — Weiterleitung zum Stripe Billing Portal."""
    email = req.rel_url.query.get("email", "")
    if not email and req.method == "POST":
        try:
            body = await req.json()
            email = body.get("email", "")
        except Exception:
            pass

    if not email or "@" not in email:
        return web.Response(
            text=_portal_form(),
            content_type="text/html",
        )

    try:
        url = await create_portal_session(email)
        raise web.HTTPFound(url)
    except web.HTTPFound:
        raise
    except Exception as e:
        log.error("Portal Fehler: %s", e)
        return web.json_response({"error": str(e)}, status=500)


def _portal_form() -> str:
    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"><title>Abo verwalten — AIITEC</title>
<style>
body{{background:#030308;color:#e2e8f0;font-family:-apple-system,sans-serif;
     display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}
.box{{background:#0d0d1a;border:1px solid #1e1e3a;border-radius:16px;padding:48px;
      text-align:center;max-width:420px;width:90%}}
h1{{font-size:22px;font-weight:800;margin-bottom:8px;color:#e2e8f0}}
p{{color:#64748b;font-size:14px;margin-bottom:24px}}
input{{width:100%;background:#030308;border:1px solid #2d2d3d;color:#e2e8f0;
       padding:14px;border-radius:8px;font-size:16px;margin-bottom:12px;box-sizing:border-box}}
input:focus{{outline:none;border-color:#6366f1}}
button{{width:100%;background:#6366f1;color:#fff;padding:14px;border-radius:8px;
        font-size:16px;font-weight:700;border:none;cursor:pointer}}
</style></head>
<body>
<div class="box">
  <div style="font-size:40px;margin-bottom:16px">⚙️</div>
  <h1>Abo verwalten</h1>
  <p>Gib deine E-Mail-Adresse ein um dein AIITEC-Abonnement zu verwalten,<br>
  Rechnungen herunterzuladen oder zu kündigen.</p>
  <form method="GET" action="/portal">
    <input type="email" name="email" placeholder="deine@email.de" required autocomplete="email">
    <button type="submit">Weiter zum Abo-Portal →</button>
  </form>
  <p style="margin-top:16px;font-size:12px">
    Powered by <strong style="color:#6366f1">Stripe</strong> · Sicher &amp; verschlüsselt
  </p>
</div>
</body></html>"""
