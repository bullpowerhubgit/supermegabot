"""PayPal Classic NVP API client for SuperMegaBot."""
import os, aiohttp, logging, urllib.parse

logger = logging.getLogger(__name__)

PAYPAL_API_USERNAME = os.getenv("PAYPAL_API_USERNAME", "")
PAYPAL_API_PASSWORD = os.getenv("PAYPAL_API_PASSWORD", "")
PAYPAL_API_SIGNATURE = os.getenv("PAYPAL_API_SIGNATURE", "")
PAYPAL_ENV = os.getenv("PAYPAL_ENVIRONMENT", "production")
PAYPAL_NVP_URL = (
    "https://api-3t.paypal.com/nvp"
    if PAYPAL_ENV == "production"
    else "https://api-3t.sandbox.paypal.com/nvp"
)
PAYPAL_WEB_URL = (
    "https://www.paypal.com/cgi-bin/webscr"
    if PAYPAL_ENV == "production"
    else "https://www.sandbox.paypal.com/cgi-bin/webscr"
)


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
    base_url = "https://dudirudibot-mega-production.up.railway.app"
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
