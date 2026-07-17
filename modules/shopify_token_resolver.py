"""
Shopify Token Resolver — startup self-healing für SHOPIFY_ACCESS_TOKEN.
Prüft ob SHOPIFY_ACCESS_TOKEN gültig ist; falls 401, ersetzt es durch
SHOPIFY_ADMIN_API_TOKEN in os.environ (nur im laufenden Prozess).
"""
import os
import logging
import urllib.request
import urllib.error

log = logging.getLogger("ShopifyTokenResolver")

_VALIDATED: bool | None = None


def _test_token(token: str, domain: str, version: str) -> bool:
    """Gibt True zurück wenn der Token für GET /blogs.json funktioniert."""
    if not token or not domain:
        return False
    url = f"https://{domain}/admin/api/{version}/shop.json"
    req = urllib.request.Request(url, headers={"X-Shopify-Access-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        return e.code != 401
    except Exception:
        return False


def enforce_valid_token() -> dict:
    """
    Stellt sicher, dass SHOPIFY_ACCESS_TOKEN im Prozess gültig ist.
    Gibt dict zurück: {"ok": bool, "source": str, "fixed": bool}
    """
    global _VALIDATED
    domain  = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    version = os.getenv("SHOPIFY_API_VERSION", "2026-04")
    primary = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    fallback = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")

    if _test_token(primary, domain, version):
        _VALIDATED = True
        return {"ok": True, "source": "SHOPIFY_ACCESS_TOKEN", "fixed": False}

    log.warning("SHOPIFY_ACCESS_TOKEN ungültig (401) — Fallback auf SHOPIFY_ADMIN_API_TOKEN")

    if fallback and _test_token(fallback, domain, version):
        os.environ["SHOPIFY_ACCESS_TOKEN"] = fallback
        _VALIDATED = True
        log.info("SHOPIFY_ACCESS_TOKEN → SHOPIFY_ADMIN_API_TOKEN gesetzt (self-heal)")
        return {"ok": True, "source": "SHOPIFY_ADMIN_API_TOKEN", "fixed": True}

    log.error("Beide Shopify-Tokens ungültig — Shop-Calls schlagen fehl!")
    _VALIDATED = False
    return {"ok": False, "source": "none", "fixed": False}


def self_check() -> dict:
    """Gibt aktuellen Validierungsstatus zurück."""
    return {"validated": _VALIDATED, "token_set": bool(os.getenv("SHOPIFY_ACCESS_TOKEN"))}
