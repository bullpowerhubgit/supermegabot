"""LinkedIn OAuth 2.0 for SuperMegaBot — w_member_social scope."""
import os, aiohttp, logging, urllib.parse

logger = logging.getLogger(__name__)

LINKEDIN_CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID", "")
LINKEDIN_CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET", "")
LINKEDIN_REDIRECT_URI = os.getenv(
    "LINKEDIN_REDIRECT_URI",
    "https://supermegabot-production.up.railway.app/api/linkedin/callback",
)
LINKEDIN_PERSON_URN = os.getenv("LINKEDIN_PERSON_URN", "urn:li:person:YcxbqVN0ZR")
LINKEDIN_SCOPES = "r_liteprofile r_emailaddress w_member_social"


def get_linkedin_auth_url() -> str:
    params = {
        "response_type": "code",
        "client_id": LINKEDIN_CLIENT_ID,
        "redirect_uri": LINKEDIN_REDIRECT_URI,
        "scope": LINKEDIN_SCOPES,
        "state": "linkedin_auth",
    }
    return f"https://www.linkedin.com/oauth/v2/authorization?{urllib.parse.urlencode(params)}"


async def exchange_code_for_token(code: str) -> dict:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
        async with s.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": LINKEDIN_REDIRECT_URI,
                "client_id": LINKEDIN_CLIENT_ID,
                "client_secret": LINKEDIN_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as r:
            return await r.json()


async def refresh_access_token() -> str | None:
    """Use refresh token to get a new access token; save to Railway env."""
    refresh_token = os.getenv("LINKEDIN_REFRESH_TOKEN", "")
    if not refresh_token or not LINKEDIN_CLIENT_ID or not LINKEDIN_CLIENT_SECRET:
        return None
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
        async with s.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": LINKEDIN_CLIENT_ID,
                "client_secret": LINKEDIN_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as r:
            data = await r.json()
            new_token = data.get("access_token")
            if new_token:
                import subprocess
                subprocess.Popen(["railway", "variables", "set",
                                  f"LINKEDIN_ACCESS_TOKEN={new_token}"])
                os.environ["LINKEDIN_ACCESS_TOKEN"] = new_token
                logger.info("LinkedIn access token refreshed via refresh_token")
                return new_token
            logger.error(f"LinkedIn token refresh failed: {data}")
            return None


async def post_to_linkedin(text: str) -> dict:
    """Post to LinkedIn; auto-refresh token on 401."""
    token = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
    person_urn = os.getenv("LINKEDIN_PERSON_URN", LINKEDIN_PERSON_URN)
    payload = {
        "author": person_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
        async with s.post("https://api.linkedin.com/v2/ugcPosts",
                          json=payload, headers=headers) as r:
            if r.status == 201 or r.status == 200:
                data = await r.json()
                return {"success": True, "post_id": data.get("id")}
            if r.status == 401:
                new_token = await refresh_access_token()
                if new_token:
                    headers["Authorization"] = f"Bearer {new_token}"
                    async with s.post("https://api.linkedin.com/v2/ugcPosts",
                                      json=payload, headers=headers) as r2:
                        if r2.status in (200, 201):
                            data = await r2.json()
                            return {"success": True, "post_id": data.get("id"), "refreshed": True}
            data = await r.json()
            return {"success": False, "status": r.status, "error": data}


async def post_article(text: str, title: str = "") -> dict:
    """Alias for post_to_linkedin with circuit breaker protection."""
    from modules.circuit_breaker import get_breaker
    cb = get_breaker("linkedin")
    if cb.is_open:
        return {"ok": False, "skipped": True, "reason": "circuit_open:linkedin"}
    result = await post_to_linkedin(text)
    if result.get("success"):
        cb.success()
    else:
        status_code = result.get("status", 0) or 0
        cb.failure(str(result.get("error", "")), int(status_code))
    return result


async def run_with_brutus_traffic(topic: str = "E-Commerce Automatisierung mit KI") -> dict:
    """Post AI-generated LinkedIn content then fire BRUTUS traffic swarm."""
    try:
        from modules.ai_client import ai_complete
        ds24 = os.getenv("DS24_AFFILIATE_LINK",
                         os.getenv("DS24_AFFILIATE_LINK", "https://www.checkout-ds24.com/product/668035"))
        prompt = (
            f"Schreibe einen professionellen LinkedIn-Post auf Deutsch über: {topic}. "
            f"Max 1200 Zeichen. Erwähne am Ende: {ds24} (AI Income Machine). Nur Text."
        )
        text = await ai_complete(prompt, max_tokens=400)
        if not text:
            text = (f"🚀 {topic} — vollautomatisch mit SuperMegaBot!\n\n"
                    f"Mehr unter: {ds24}\n\n#KI #Ecommerce #Automation")
    except Exception as e:
        logger.warning("LinkedIn AI content fallback: %s", e)
        ds24 = os.getenv("DS24_AFFILIATE_LINK",
                         os.getenv("DS24_AFFILIATE_LINK", "https://www.checkout-ds24.com/product/668035"))
        text = (f"🚀 E-Commerce Automatisierung mit KI — SuperMegaBot!\n\n"
                f"Mehr unter: {ds24}\n\n#KI #Ecommerce #Automation")

    linkedin_result = await post_article(text)

    brutus_result = {}
    try:
        from modules.brutus_traffic_engine import run_brutus_swarm
        brutus_result = await run_brutus_swarm(
            niche=topic,
            affiliate_url=os.getenv("DS24_AFFILIATE_LINK",
                                    os.getenv("DS24_AFFILIATE_LINK", "https://www.checkout-ds24.com/product/668035")),
        )
    except Exception as e:
        brutus_result = {"error": str(e)}

    return {"linkedin": linkedin_result, "brutus": brutus_result}


async def get_linkedin_status() -> dict:
    token = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
    if not token:
        return {
            "connected": False,
            "needs_app_setup": not bool(LINKEDIN_CLIENT_ID),
            "auth_url": get_linkedin_auth_url() if LINKEDIN_CLIENT_ID else None,
            "message": "Set LINKEDIN_ACCESS_TOKEN in Railway",
        }
    # Test with /v2/userinfo (lightweight, works with any valid token)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
        async with s.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {token}"},
        ) as r:
            if r.status == 200:
                d = await r.json(content_type=None)
                return {"connected": True, "token_present": True,
                        "name": d.get("name", ""), "email": d.get("email", ""),
                        "note": "Token valid (userinfo OK)"}
            if r.status == 401:
                new_token = await refresh_access_token()
                return {"connected": bool(new_token), "refreshed": bool(new_token)}
            return {"connected": False, "http_status": r.status}
