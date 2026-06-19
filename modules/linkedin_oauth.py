"""LinkedIn OAuth 2.0 for SuperMegaBot — w_member_social scope."""
import os, aiohttp, logging, urllib.parse

logger = logging.getLogger(__name__)

LINKEDIN_CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID", "")
LINKEDIN_CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET", "")
LINKEDIN_REDIRECT_URI = os.getenv(
    "LINKEDIN_REDIRECT_URI",
    "https://dudirudibot-mega-production.up.railway.app/api/linkedin/callback",
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


async def get_linkedin_status() -> dict:
    token = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
    if not token:
        return {
            "connected": False,
            "needs_app_setup": not bool(LINKEDIN_CLIENT_ID),
            "auth_url": get_linkedin_auth_url() if LINKEDIN_CLIENT_ID else None,
            "message": (
                "Visit /api/linkedin/auth to authorize"
                if LINKEDIN_CLIENT_ID
                else "Set LINKEDIN_CLIENT_ID + LINKEDIN_CLIENT_SECRET in Railway first"
            ),
        }
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
        async with s.get(
            "https://api.linkedin.com/v2/me",
            headers={"Authorization": f"Bearer {token}"},
        ) as r:
            if r.status == 200:
                data = await r.json()
                return {"connected": True, "profile": data.get("localizedFirstName", "Rudolf")}
            return {"connected": False, "http_status": r.status, "expired": True}
