"""
Google Merchant Center Feed Auto-Submitter
Registriert den Google Shopping Feed bei GMC und scheduled tägliche Updates.
EINMALIG: Content API for Shopping muss aktiviert sein:
https://console.developers.google.com/apis/api/shoppingcontent.googleapis.com/overview?project=636911122314
"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path

import aiohttp

log = logging.getLogger("GMCFeedSubmitter")

GMC_MERCHANT_ID = os.getenv("GMC_MERCHANT_ID", "5734366162")
FEED_URL = os.getenv(
    "GMC_FEED_URL",
    "https://supermegabot-production.up.railway.app/feed/google-shopping.xml"
)
SA_FILE = Path(os.getenv(
    "GOOGLE_APPLICATION_CREDENTIALS",
    "/Users/rudolfsarkany/supermegabot/credentials/yt-tracker-sa.json"
))


async def _get_access_token() -> str:
    """JWT-basierter Service Account Token für Content API."""
    import json as json_mod
    import time as time_mod
    import base64, hashlib, hmac

    try:
        import jwt  # PyJWT
    except ImportError:
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.hazmat.backends import default_backend
        except ImportError:
            raise RuntimeError("PyJWT oder cryptography Package fehlt — pip3 install PyJWT cryptography")

    if not SA_FILE.exists():
        raise FileNotFoundError(f"Service Account nicht gefunden: {SA_FILE}")

    sa_data = json_mod.loads(SA_FILE.read_text())
    now = int(time_mod.time())
    claim = {
        "iss": sa_data["client_email"],
        "scope": "https://www.googleapis.com/auth/content",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
    }

    try:
        import jwt as pyjwt
        signed = pyjwt.encode(claim, sa_data["private_key"], algorithm="RS256")
    except Exception:
        # Fallback: cryptography direkt
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import padding as cp
        from cryptography.hazmat.primitives import hashes as ch
        import base64 as b64, json as js

        header = b64.urlsafe_b64encode(js.dumps({"alg":"RS256","typ":"JWT"}).encode()).rstrip(b"=")
        payload = b64.urlsafe_b64encode(js.dumps(claim).encode()).rstrip(b"=")
        msg = header + b"." + payload
        key = serialization.load_pem_private_key(sa_data["private_key"].encode(), password=None)
        sig = key.sign(msg, cp.PKCS1v15(), ch.SHA256())
        sig_b64 = b64.urlsafe_b64encode(sig).rstrip(b"=")
        signed = (msg + b"." + sig_b64).decode()

    async with aiohttp.ClientSession() as s:
        async with s.post(
            "https://oauth2.googleapis.com/token",
            data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": signed},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            resp = await r.json()
            if "access_token" not in resp:
                raise RuntimeError(f"Token-Fehler: {resp}")
            return resp["access_token"]


async def list_feeds(token: str) -> list:
    async with aiohttp.ClientSession() as s:
        async with s.get(
            f"https://shoppingcontent.googleapis.com/content/v2.1/{GMC_MERCHANT_ID}/datafeeds",
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            data = await r.json()
            return data.get("resources", [])


async def register_feed(token: str) -> dict:
    """Feed im GMC registrieren falls noch nicht vorhanden."""
    feeds = await list_feeds(token)
    for f in feeds:
        if "ineedit" in f.get("name", "").lower() or FEED_URL in str(f.get("fetchSchedule", {})):
            log.info("Feed bereits registriert: %s", f.get("id"))
            return f

    body = {
        "name": "ineedit-smart-products",
        "contentType": "products",
        "contentLanguage": "de",
        "targetCountry": "DE",
        "fetchSchedule": {
            "weekday": "monday",
            "hour": 6,
            "timeZone": "Europe/Berlin",
            "fetchUrl": FEED_URL,
            "paused": False,
        },
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"https://shoppingcontent.googleapis.com/content/v2.1/{GMC_MERCHANT_ID}/datafeeds",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            result = await r.json()
            if "id" in result:
                log.info("Feed registriert! ID: %s", result["id"])
            else:
                log.error("Fehler beim Registrieren: %s", result)
            return result


async def trigger_fetch(token: str, feed_id: str) -> dict:
    """Sofortigen Feed-Fetch im GMC auslösen."""
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"https://shoppingcontent.googleapis.com/content/v2.1/{GMC_MERCHANT_ID}/datafeeds/{feed_id}/fetchNow",
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            return await r.json()


async def run_gmc_setup():
    """Vollständiger GMC-Setup: Token → Feed registrieren → sofort fetchen."""
    log.info("GMC Setup startet...")
    try:
        token = await _get_access_token()
        log.info("✅ Token erhalten")

        result = await register_feed(token)
        feed_id = result.get("id")
        if feed_id:
            log.info("✅ Feed registriert: %s", feed_id)
            fetch = await trigger_fetch(token, feed_id)
            log.info("✅ Sofort-Fetch ausgelöst: %s", fetch)
            return {"status": "ok", "feed_id": feed_id, "fetch": fetch}
        else:
            return {"status": "error", "detail": result}
    except Exception as e:
        log.error("GMC Setup Fehler: %s", e)
        return {"status": "error", "detail": str(e)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = asyncio.run(run_gmc_setup())
    print(json.dumps(result, indent=2, ensure_ascii=False))
