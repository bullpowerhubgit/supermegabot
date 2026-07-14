"""Shopify Client Credentials Token Manager — auto-refresh alle 24h"""
import os, time, logging
from urllib.request import urlopen, Request
from urllib.parse import urlencode
import json
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

log = logging.getLogger("ShopifyToken")

SHOP   = os.getenv("SHOPIFY_SHOP", "ineedit.com.co")
CID    = os.getenv("SHOPIFY_CREDENTIALS_CLIENT_ID", "")
CSEC   = os.getenv("SHOPIFY_CREDENTIALS_CLIENT_SECRET", "")

_cache = {"token": None, "expires_at": 0}

def get_token() -> str:
    if _cache["token"] and time.time() < _cache["expires_at"] - 60:
        return _cache["token"]
    data = urlencode({
        "grant_type": "client_credentials",
        "client_id": CID,
        "client_secret": CSEC,
    }).encode()
    req = Request(
        f"https://{SHOP}.myshopify.com/admin/oauth/access_token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(req, timeout=10) as r:
        d = json.loads(r.read())
    _cache["token"] = d["access_token"]
    _cache["expires_at"] = time.time() + d.get("expires_in", 86399)
    log.info("Shopify token refreshed, expires in %ds", d.get("expires_in", 86399))
    return _cache["token"]

def auth_headers() -> dict:
    return {"X-Shopify-Access-Token": get_token()}
