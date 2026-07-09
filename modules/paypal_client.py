"""PayPal NVP + REST API client for SuperMegaBot."""
import os, aiohttp, logging, urllib.parse, base64

logger = logging.getLogger(__name__)

# Support both PAYPAL_MODE and PAYPAL_ENVIRONMENT env var names
_mode = os.getenv("PAYPAL_MODE") or os.getenv("PAYPAL_ENVIRONMENT", "sandbox")
_is_sandbox = _mode.lower() in ("sandbox", "test")

# ── NVP/SOAP (Classic) — auto-selects sandbox vs live ─────────────────────────
if _is_sandbox:
    PAYPAL_API_USERNAME  = os.getenv("PAYPAL_SANDBOX_USERNAME",  "")
    PAYPAL_API_PASSWORD  = os.getenv("PAYPAL_SANDBOX_PASSWORD",  "")
    PAYPAL_API_SIGNATURE = os.getenv("PAYPAL_SANDBOX_SIGNATURE", "")
else:
    PAYPAL_API_USERNAME  = os.getenv("PAYPAL_API_USERNAME",  "")
    PAYPAL_API_PASSWORD  = os.getenv("PAYPAL_API_PASSWORD",  "")
    PAYPAL_API_SIGNATURE = os.getenv("PAYPAL_API_SIGNATURE", "")

# ── REST API ──────────────────────────────────────────────────────────────────
PAYPAL_REST_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_REST_SECRET    = os.getenv("PAYPAL_CLIENT_SECRET") or os.getenv("PAYPAL_SECRET", "")

PAYPAL_REST_BASE = "https://api-m.sandbox.paypal.com" if _is_sandbox else "https://api-m.paypal.com"
PAYPAL_NVP_URL   = "https://api-3t.sandbox.paypal.com/nvp" if _is_sandbox else "https://api-3t.paypal.com/nvp"
PAYPAL_WEB_URL   = "https://www.sandbox.paypal.com/cgi-bin/webscr" if _is_sandbox else "https://www.paypal.com/cgi-bin/webscr"


async def get_rest_token() -> str | None:
    """Get PayPal REST OAuth2 access token."""
    creds = base64.b64encode(f"{PAYPAL_REST_CLIENT_ID}:{PAYPAL_REST_SECRET}".encode()).decode()
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post(
                f"{PAYPAL_REST_BASE}/v1/oauth2/token",
                headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"},
                data="grant_type=client_credentials",
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    return d.get("access_token")
    except Exception as e:
        logger.debug("PayPal token error: %s", e)
    return None


async def nvp_call(method: str, params: dict) -> dict:
    base = {
        "METHOD": method,
        "VERSION": "204",
        "USER": PAYPAL_API_USERNAME,
        "PWD": PAYPAL_API_PASSWORD,
        "SIGNATURE": PAYPAL_API_SIGNATURE,
    }
    base.update(params)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
        async with s.post(PAYPAL_NVP_URL, data=base) as r:
            text = await r.text()
            return dict(urllib.parse.parse_qsl(text))


async def create_checkout(amount: float, currency: str = "EUR",
                          item_name: str = "SuperMegaBot",
                          notify_url: str = "") -> dict:
    base_url = "https://supermegabot-production.up.railway.app"
    params = {
        "PAYMENTACTION": "Sale",
        "AMT": f"{amount:.2f}",
        "CURRENCYCODE": currency,
        "L_PAYMENTREQUEST_0_NAME0": item_name,
        "L_PAYMENTREQUEST_0_AMT0": f"{amount:.2f}",
        "RETURNURL": os.getenv("PAYPAL_RETURN_URL", f"{base_url}/api/paypal/success"),
        "CANCELURL": os.getenv("PAYPAL_CANCEL_URL", f"{base_url}/api/paypal/cancel"),
        "NOTIFYURL": notify_url or os.getenv("PAYPAL_IPN_URL", f"{base_url}/api/paypal/ipn"),
    }
    result = await nvp_call("SetExpressCheckout", params)
    if result.get("ACK", "").startswith("Success"):
        token = result["TOKEN"]
        return {
            "success": True,
            "token": token,
            "redirect_url": f"{PAYPAL_WEB_URL}?cmd=_express-checkout&token={token}",
        }
    return {"success": False, "error": result.get("L_LONGMESSAGE0", "Unknown error")}


async def verify_ipn(params: dict) -> bool:
    verify_params = {"cmd": "_notify-validate"}
    verify_params.update(params)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
        async with s.post("https://ipnpb.paypal.com/cgi-bin/webscr", data=verify_params) as r:
            return (await r.text()) == "VERIFIED"


async def get_paypal_status() -> dict:
    if not all([PAYPAL_API_USERNAME, PAYPAL_API_PASSWORD, PAYPAL_API_SIGNATURE]):
        return {"connected": False, "reason": "missing credentials"}
    result = await nvp_call("GetPalDetails", {})
    return {
        "connected": result.get("ACK", "").startswith("Success"),
        "ack": result.get("ACK"),
        "env": PAYPAL_ENV,
        "email": result.get("EMAIL", ""),
    }


async def get_status() -> str:
    """Rudibot-friendly status string."""
    # Try REST token first
    token = await get_rest_token()
    rest_ok = bool(token)

    # Try NVP
    try:
        nvp_result = await nvp_call("GetPalDetails", {})
        nvp_ok = nvp_result.get("ACK", "").startswith("Success")
        nvp_email = nvp_result.get("EMAIL", "?")
    except Exception:
        nvp_ok, nvp_email = False, "?"

    env_label = "🧪 Sandbox" if _is_sandbox else "🔴 LIVE"
    rest_label = "✅ OK" if rest_ok else "❌ FEHLT (LIVE keys nötig)"
    nvp_label  = f"✅ {nvp_email}" if nvp_ok else "❌ NVP fehlt"

    live_hint = "" if not _is_sandbox else "\n⚠️ LIVE Keys: developer.paypal.com → RudiBot → LIVE Tab"
    return (
        f"💳 PayPal {env_label}\n"
        f"REST API: {rest_label}\n"
        f"NVP/SOAP: {nvp_label}"
        f"{live_hint}"
    )


async def create_order(amount: float, currency: str = "EUR", description: str = "SuperMegaBot") -> dict:
    """REST API: Create PayPal Order (checkout)."""
    token = await get_rest_token()
    if not token:
        return {"ok": False, "error": "no access token"}
    base_url = "https://supermegabot-production.up.railway.app"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(
                f"{PAYPAL_REST_BASE}/v2/checkout/orders",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "intent": "CAPTURE",
                    "purchase_units": [{"amount": {"currency_code": currency, "value": f"{amount:.2f}"}, "description": description}],
                    "application_context": {
                        "return_url": f"{base_url}/api/paypal/success",
                        "cancel_url": f"{base_url}/api/paypal/cancel",
                    },
                },
            ) as r:
                d = await r.json()
                if r.status in (200, 201):
                    order_id = d.get("id")
                    approve_url = next((l["href"] for l in d.get("links", []) if l.get("rel") == "approve"), None)
                    return {"ok": True, "order_id": order_id, "approve_url": approve_url}
                return {"ok": False, "error": str(d)[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)}
