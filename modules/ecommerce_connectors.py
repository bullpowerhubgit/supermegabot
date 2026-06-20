#!/usr/bin/env python3
"""
Ecommerce Connectors — Unified async clients for Etsy, Gumroad, Fiverr, Indeed.

Setup:
  Etsy:    https://www.etsy.com/developers/register
           ENV: ETSY_API_KEY, ETSY_ACCESS_TOKEN, ETSY_SHOP_ID
  Gumroad: https://app.gumroad.com/api
           ENV: GUMROAD_ACCESS_TOKEN
  Fiverr:  https://developers.fiverr.com  (API sehr eingeschränkt, manuelle Genehmigung nötig)
           ENV: FIVERR_CLIENT_ID, FIVERR_CLIENT_SECRET
  Indeed:  https://ads.indeed.com/jobroll/xmlfeed
           ENV: INDEED_PUBLISHER_ID
"""

import logging
import os
from typing import Any, Dict, List, Optional

log = logging.getLogger("EcommerceConnectors")

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    log.warning("aiohttp nicht installiert — HTTP-Calls nicht möglich. `pip install aiohttp`")

_TIMEOUT = aiohttp.ClientTimeout(total=20) if HAS_AIOHTTP else None


def _session():
    return aiohttp.ClientSession(timeout=_TIMEOUT)


# ---------------------------------------------------------------------------
# Etsy Connector
# ---------------------------------------------------------------------------

class EtsyConnector:
    """
    Async client for the Etsy Open API v3.

    Required ENV vars:
      ETSY_API_KEY      — OAuth2 client key (x-api-key header)
      ETSY_ACCESS_TOKEN — OAuth2 Bearer token
      ETSY_SHOP_ID      — numeric shop ID (e.g. 12345678)

    Register at: https://www.etsy.com/developers/register
    """

    BASE = "https://openapi.etsy.com/v3"

    def __init__(self):
        self.api_key = os.getenv("ETSY_API_KEY", "")
        self.access_token = os.getenv("ETSY_ACCESS_TOKEN", "")
        self.shop_id = os.getenv("ETSY_SHOP_ID", "")
        if not self.api_key:
            log.debug("ETSY_API_KEY not set — Etsy disabled (banned app)")

    def _headers(self) -> Dict[str, str]:
        h = {"x-api-key": self.api_key}
        if self.access_token:
            h["Authorization"] = f"Bearer {self.access_token}"
        return h

    def _ok(self) -> bool:
        return bool(self.api_key and HAS_AIOHTTP)

    async def _get(self, path: str, params: Optional[Dict] = None) -> Dict:
        if not self._ok():
            raise RuntimeError("EtsyConnector: ETSY_API_KEY fehlt oder aiohttp nicht installiert")
        url = f"{self.BASE}{path}"
        async with _session() as s:
            async with s.get(url, headers=self._headers(), params=params or {}) as r:
                if r.status == 401:
                    raise PermissionError("Etsy 401 — ETSY_ACCESS_TOKEN ungültig oder abgelaufen")
                r.raise_for_status()
                return await r.json()

    async def _post(self, path: str, data: Dict) -> Dict:
        if not self._ok():
            raise RuntimeError("EtsyConnector: ETSY_API_KEY fehlt oder aiohttp nicht installiert")
        url = f"{self.BASE}{path}"
        async with _session() as s:
            async with s.post(url, headers={**self._headers(), "Content-Type": "application/json"},
                              json=data) as r:
                if r.status == 401:
                    raise PermissionError("Etsy 401 — ETSY_ACCESS_TOKEN ungültig oder abgelaufen")
                r.raise_for_status()
                return await r.json()

    async def ping(self) -> Dict[str, Any]:
        """Test connectivity — GET /application/users/me"""
        try:
            data = await self._get("/application/users/me")
            return {"connected": True, "user_id": data.get("user_id"), "email": data.get("primary_email")}
        except Exception as e:
            return {"connected": False, "error": str(e)}

    async def get_listings(self, state: str = "active", limit: int = 25) -> List[Dict]:
        """
        Return shop listings filtered by state.

        Args:
            state: "active" | "inactive" | "draft" | "expired" | "sold_out"
            limit: max results (1–100)
        """
        if not self.shop_id:
            log.debug("ETSY_SHOP_ID not set — Etsy disabled")
            return []
        data = await self._get(
            f"/application/shops/{self.shop_id}/listings",
            params={"state": state, "limit": limit},
        )
        return data.get("results", [])

    async def create_listing(
        self,
        title: str,
        description: str,
        price: float,
        quantity: int,
        tags: List[str],
    ) -> Dict:
        """
        Create a new Etsy listing in the configured shop.

        Args:
            title:       listing title (max 140 chars)
            description: full listing description
            price:       price in USD (e.g. 29.99)
            quantity:    available quantity
            tags:        up to 13 tags (each max 20 chars)
        """
        if not self.shop_id:
            raise ValueError("ETSY_SHOP_ID fehlt")
        payload = {
            "title": title[:140],
            "description": description,
            "price": round(price, 2),
            "quantity": quantity,
            "tags": tags[:13],
            "who_made": "i_did",
            "when_made": "made_to_order",
            "taxonomy_id": 1,  # generic — caller should override per category
            "type": "physical",
            "state": "draft",   # start as draft for safety
        }
        return await self._post(f"/application/shops/{self.shop_id}/listings", payload)

    async def get_stats(self) -> Dict[str, Any]:
        """Return summary: listing count + featured count."""
        try:
            all_listings = await self.get_listings(state="active", limit=100)
            featured = [l for l in all_listings if l.get("featured_rank") is not None]
            return {
                "total_active": len(all_listings),
                "featured_count": len(featured),
            }
        except Exception as e:
            return {"error": str(e)}

    async def get_transactions(self, limit: int = 10) -> List[Dict]:
        """Return recent shop transactions (sales)."""
        if not self.shop_id:
            log.debug("ETSY_SHOP_ID not set — Etsy disabled")
            return []
        data = await self._get(
            f"/application/shops/{self.shop_id}/transactions",
            params={"limit": limit},
        )
        return data.get("results", [])


# ---------------------------------------------------------------------------
# Gumroad Connector
# ---------------------------------------------------------------------------

class GumroadConnector:
    """
    Async client for the Gumroad API v2.

    Required ENV vars:
      GUMROAD_ACCESS_TOKEN — OAuth token from your Gumroad app

    API docs / register: https://app.gumroad.com/api
    """

    BASE = "https://api.gumroad.com/v2"

    def __init__(self):
        self.token = os.getenv("GUMROAD_ACCESS_TOKEN", "")
        if not self.token:
            log.warning(
                "GUMROAD_ACCESS_TOKEN fehlt — Gumroad-Funktionen nicht verfügbar. "
                "API-Zugang: https://app.gumroad.com/api"
            )

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def _ok(self) -> bool:
        return bool(self.token and HAS_AIOHTTP)

    async def _get(self, path: str, params: Optional[Dict] = None) -> Dict:
        if not self._ok():
            raise RuntimeError("GumroadConnector: GUMROAD_ACCESS_TOKEN fehlt")
        async with _session() as s:
            async with s.get(f"{self.BASE}{path}", headers=self._headers(),
                             params=params or {}) as r:
                if r.status == 401:
                    raise PermissionError("Gumroad 401 — Token ungültig")
                r.raise_for_status()
                return await r.json()

    async def _post(self, path: str, data: Dict) -> Dict:
        if not self._ok():
            raise RuntimeError("GumroadConnector: GUMROAD_ACCESS_TOKEN fehlt")
        async with _session() as s:
            async with s.post(f"{self.BASE}{path}", headers=self._headers(), data=data) as r:
                if r.status == 401:
                    raise PermissionError("Gumroad 401 — Token ungültig")
                r.raise_for_status()
                return await r.json()

    async def ping(self) -> Dict[str, Any]:
        """Test connectivity — GET /user"""
        try:
            data = await self._get("/user")
            user = data.get("user", {})
            return {
                "connected": data.get("success", False),
                "name": user.get("display_name"),
                "email": user.get("email"),
            }
        except Exception as e:
            return {"connected": False, "error": str(e)}

    async def get_products(self) -> List[Dict]:
        """Return all products for the authenticated seller."""
        data = await self._get("/products")
        return data.get("products", [])

    async def create_product(
        self,
        name: str,
        price_cents: int,
        description: str,
        url: str = "",
    ) -> Dict:
        """
        Create a new Gumroad product.

        Args:
            name:        product title
            price_cents: price in cents (0 = pay-what-you-want)
            description: product description (HTML allowed)
            url:         custom permalink slug (optional)
        """
        payload: Dict[str, Any] = {
            "name": name,
            "price": price_cents,
            "description": description,
        }
        if url:
            payload["url"] = url
        return await self._post("/products", payload)

    async def get_sales(self, after: str = "", before: str = "") -> List[Dict]:
        """
        Return sales records, optionally filtered by date range.

        Args:
            after:  ISO date string e.g. "2024-01-01"
            before: ISO date string e.g. "2024-12-31"
        """
        params: Dict[str, str] = {}
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        data = await self._get("/sales", params=params)
        return data.get("sales", [])

    async def get_stats(self) -> Dict[str, Any]:
        """Return total sales count and cumulative revenue (USD cents)."""
        try:
            sales = await self.get_sales()
            total_revenue = sum(int(s.get("price", 0)) for s in sales)
            return {
                "total_sales": len(sales),
                "total_revenue_cents": total_revenue,
                "total_revenue_usd": round(total_revenue / 100, 2),
            }
        except Exception as e:
            return {"error": str(e)}


# ---------------------------------------------------------------------------
# Fiverr Connector
# ---------------------------------------------------------------------------

class FiverrConnector:
    """
    Best-effort async client for Fiverr.

    NOTE: The Fiverr REST API is extremely limited and requires manual approval
    from Fiverr for production access. Most endpoints are unavailable without
    special partnership status.

    Required ENV vars:
      FIVERR_CLIENT_ID     — from your Fiverr app
      FIVERR_CLIENT_SECRET — from your Fiverr app

    Apply at: https://developers.fiverr.com
    """

    BASE = "https://api.fiverr.com/v1"

    def __init__(self):
        self.client_id = os.getenv("FIVERR_CLIENT_ID", "")
        self.client_secret = os.getenv("FIVERR_CLIENT_SECRET", "")
        if not (self.client_id and self.client_secret):
            log.warning(
                "FIVERR_CLIENT_ID / FIVERR_CLIENT_SECRET fehlt. "
                "Fiverr API erfordert manuelle Genehmigung — https://developers.fiverr.com"
            )

    def _ok(self) -> bool:
        return bool(self.client_id and self.client_secret and HAS_AIOHTTP)

    async def ping(self) -> Dict[str, Any]:
        """
        Try to reach the Fiverr profile endpoint.
        Returns connected=False with a helpful message if the API is unavailable
        (which is the default state without manual approval).
        """
        if not self._ok():
            return {
                "connected": False,
                "message": (
                    "Fiverr API erfordert manuelle Genehmigung. "
                    "Bewerbung unter https://developers.fiverr.com"
                ),
            }
        try:
            headers = {
                "client-id": self.client_id,
                "client-secret": self.client_secret,
            }
            async with _session() as s:
                async with s.get(f"{self.BASE}/profile", headers=headers) as r:
                    if r.status in (401, 403, 404):
                        return {
                            "connected": False,
                            "message": (
                                f"Fiverr API HTTP {r.status} — "
                                "Fiverr API erfordert manuelle Genehmigung. "
                                "Bewerbung unter https://developers.fiverr.com"
                            ),
                        }
                    r.raise_for_status()
                    data = await r.json()
                    return {"connected": True, "data": data}
        except Exception as e:
            return {
                "connected": False,
                "message": (
                    "Fiverr API erfordert manuelle Genehmigung. "
                    "Bewerbung unter https://developers.fiverr.com"
                ),
                "error": str(e),
            }

    async def get_gigs(self) -> List[Dict]:
        """
        Return gigs (mock data — Fiverr has no public gig listing API).

        Fiverr's API does not expose seller gig data publicly. This returns
        sample structure so the rest of the workflow can continue in demo mode.
        """
        log.info("Fiverr hat keine öffentliche Gig-API — Beispieldaten werden zurückgegeben")
        return [
            {
                "id": "mock_gig_1",
                "title": "I will create a professional logo design",
                "price_usd": 50,
                "category": "Graphics & Design",
                "rating": 4.9,
                "orders_in_queue": 3,
                "note": "Beispieldaten — Fiverr Gig-API nicht öffentlich verfügbar",
            },
            {
                "id": "mock_gig_2",
                "title": "I will develop a Shopify store",
                "price_usd": 150,
                "category": "Programming & Tech",
                "rating": 5.0,
                "orders_in_queue": 1,
                "note": "Beispieldaten — Fiverr Gig-API nicht öffentlich verfügbar",
            },
        ]


# ---------------------------------------------------------------------------
# Indeed Connector
# ---------------------------------------------------------------------------

class IndeedConnector:
    """
    Async client for the Indeed Publisher API (read-only job search).

    Required ENV vars:
      INDEED_PUBLISHER_ID — your Indeed publisher ID

    Apply at: https://ads.indeed.com/jobroll/xmlfeed
    NOTE: The XML Publisher API has been deprecated for new publishers.
          If your account lacks API access, ping() will return connected=False.
    """

    BASE = "https://api.indeed.com/ads/apisearch"

    def __init__(self):
        self.publisher_id = os.getenv("INDEED_PUBLISHER_ID", "")
        if not self.publisher_id:
            log.warning(
                "INDEED_PUBLISHER_ID fehlt — Indeed-Jobsuche nicht verfügbar. "
                "Publisher-Programm: https://ads.indeed.com/jobroll/xmlfeed"
            )

    def _ok(self) -> bool:
        return bool(self.publisher_id and HAS_AIOHTTP)

    async def search_jobs(
        self,
        query: str,
        location: str = "Deutschland",
        limit: int = 10,
    ) -> List[Dict]:
        """
        Search for jobs via the Indeed Publisher API.

        Args:
            query:    job search keywords (e.g. "Python Developer")
            location: city or country string
            limit:    max results (1–25)

        Returns list of job dicts with keys: jobtitle, company, location, url, date, snippet.
        """
        if not self._ok():
            log.warning("INDEED_PUBLISHER_ID fehlt oder aiohttp fehlt")
            return []
        params = {
            "publisher": self.publisher_id,
            "q": query,
            "l": location,
            "limit": min(limit, 25),
            "v": "2",
            "format": "json",
            "co": "de",
            "latlong": 1,
        }
        try:
            async with _session() as s:
                async with s.get(self.BASE, params=params) as r:
                    if r.status in (401, 403):
                        log.warning(
                            "Indeed API %d — Publisher-Zugang nicht genehmigt. "
                            "https://ads.indeed.com/jobroll/xmlfeed", r.status
                        )
                        return []
                    r.raise_for_status()
                    data = await r.json()
                    return data.get("results", [])
        except Exception as e:
            log.error("Indeed search_jobs Fehler: %s", e)
            return []

    async def ping(self) -> Dict[str, Any]:
        """Test connectivity with a simple search for 'developer' in Deutschland."""
        if not self._ok():
            return {
                "connected": False,
                "message": (
                    "INDEED_PUBLISHER_ID fehlt. "
                    "Publisher-Zugang: https://ads.indeed.com/jobroll/xmlfeed"
                ),
            }
        results = await self.search_jobs("developer", location="Deutschland", limit=1)
        if results is not None:
            return {"connected": True, "test_results": len(results)}
        return {
            "connected": False,
            "message": "Indeed API nicht erreichbar — Publisher-Genehmigung prüfen",
        }


# ---------------------------------------------------------------------------
# Convenience: quick-check all connectors
# ---------------------------------------------------------------------------

async def ping_all() -> Dict[str, Any]:
    """Ping every connector and return a combined status dict."""
    etsy = EtsyConnector()
    gumroad = GumroadConnector()
    fiverr = FiverrConnector()
    indeed = IndeedConnector()

    import asyncio
    results = await asyncio.gather(
        etsy.ping(),
        gumroad.ping(),
        fiverr.ping(),
        indeed.ping(),
        return_exceptions=True,
    )
    return {
        "etsy": results[0] if not isinstance(results[0], Exception) else {"connected": False, "error": str(results[0])},
        "gumroad": results[1] if not isinstance(results[1], Exception) else {"connected": False, "error": str(results[1])},
        "fiverr": results[2] if not isinstance(results[2], Exception) else {"connected": False, "error": str(results[2])},
        "indeed": results[3] if not isinstance(results[3], Exception) else {"connected": False, "error": str(results[3])},
    }
