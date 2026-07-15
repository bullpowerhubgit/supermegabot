"""
Shopify Webhook Auto-Registrar
Registers and manages Shopify webhooks via Admin API 2024-01.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

# Load dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.debug("dotenv loaded successfully")
except ImportError:
    logger.debug("python-dotenv not available, using os.environ only")


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _get_shop_domain() -> str:
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    if not domain:
        raise ValueError("SHOPIFY_SHOP_DOMAIN environment variable is not set")
    return domain.strip().rstrip("/")


def _get_admin_token() -> str:
    token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    if not token:
        raise ValueError("SHOPIFY_ADMIN_API_TOKEN environment variable is not set")
    return token.strip()


def _api_base(shop_domain: str) -> str:
    return f"https://{shop_domain}/admin/api/2024-01/webhooks.json"


# ---------------------------------------------------------------------------
# Webhook definitions
# ---------------------------------------------------------------------------

WEBHOOK_TOPICS = [
    ("checkouts/create",    "/api/webhooks/shopify/checkout-create"),
    ("checkouts/update",    "/api/webhooks/shopify/checkout-update"),
    ("orders/create",       "/api/webhooks/shopify/order-create"),
    ("orders/paid",         "/api/webhooks/shopify/order-paid"),
    ("orders/cancelled",    "/api/webhooks/shopify/order-cancelled"),
    ("customers/create",    "/api/shopify/customer-webhook"),
]


# ---------------------------------------------------------------------------
# Low-level HTTP helpers
# ---------------------------------------------------------------------------

def _make_headers(admin_token: str) -> dict:
    return {
        "X-Shopify-Access-Token": admin_token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _http_get(url: str, headers: dict, retries: int = 3) -> dict:
    """Perform an HTTP GET with retry on rate limit."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                retry_after = float(exc.headers.get("Retry-After", "2"))
                logger.warning("Rate limited on GET %s — sleeping %.1fs (attempt %d/%d)",
                               url, retry_after, attempt, retries)
                time.sleep(retry_after)
                continue
            if exc.code == 401:
                logger.error("401 Unauthorized on GET %s — check SHOPIFY_ADMIN_API_TOKEN", url)
                raise
            body = exc.read().decode("utf-8", errors="replace")
            logger.error("HTTP %d on GET %s: %s", exc.code, url, body)
            raise
        except Exception as exc:
            logger.error("Unexpected error on GET %s: %s", url, exc)
            raise
    raise RuntimeError(f"GET {url} failed after {retries} retries (rate limit)")


def _http_post(url: str, headers: dict, payload: dict, retries: int = 3) -> tuple[int, dict]:
    """Perform an HTTP POST, return (status_code, response_body_dict)."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8")
                return resp.status, json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                retry_after = float(exc.headers.get("Retry-After", "2"))
                logger.warning("Rate limited on POST %s — sleeping %.1fs (attempt %d/%d)",
                               url, retry_after, attempt, retries)
                time.sleep(retry_after)
                continue
            body = exc.read().decode("utf-8", errors="replace")
            return exc.code, json.loads(body) if body else {}
        except Exception as exc:
            logger.error("Unexpected error on POST %s: %s", url, exc)
            raise
    raise RuntimeError(f"POST {url} failed after {retries} retries (rate limit)")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register_all_webhooks(base_url: str) -> list[dict]:
    """
    Register all required Shopify webhooks pointing to base_url.
    Returns a list of result dicts (one per topic) with keys:
      topic, address, status, message
    """
    base_url = base_url.rstrip("/")
    try:
        shop_domain = _get_shop_domain()
        admin_token = _get_admin_token()
    except ValueError as exc:
        logger.error("Configuration error: %s", exc)
        raise

    api_url = _api_base(shop_domain)
    headers = _make_headers(admin_token)
    results = []

    logger.info("Registering %d webhooks for shop %s → %s",
                len(WEBHOOK_TOPICS), shop_domain, base_url)

    for topic, path in WEBHOOK_TOPICS:
        address = base_url + path
        payload = {"webhook": {"topic": topic, "address": address, "format": "json"}}

        logger.debug("Registering webhook: topic=%s address=%s", topic, address)
        status_code, resp_body = _http_post(api_url, headers, payload)

        if status_code in (200, 201):
            hook = resp_body.get("webhook", {})
            logger.info("Registered webhook id=%s topic=%s address=%s",
                        hook.get("id"), topic, address)
            results.append({
                "topic": topic,
                "address": address,
                "status": "registered",
                "id": hook.get("id"),
                "message": "Created successfully",
            })

        elif status_code == 422:
            errors = resp_body.get("errors", {})
            address_errors = errors.get("address", [])
            # 422 "Address for this topic has already been taken" = already registered
            if any("taken" in str(e).lower() or "already" in str(e).lower()
                   for e in address_errors):
                logger.info("Webhook already registered: topic=%s address=%s", topic, address)
                results.append({
                    "topic": topic,
                    "address": address,
                    "status": "already_exists",
                    "id": None,
                    "message": "Already registered (skipped)",
                })
            else:
                logger.warning("422 Unprocessable for topic=%s: %s", topic, errors)
                results.append({
                    "topic": topic,
                    "address": address,
                    "status": "error_422",
                    "id": None,
                    "message": f"422 errors: {errors}",
                })

        elif status_code == 401:
            logger.error("401 Unauthorized — SHOPIFY_ADMIN_API_TOKEN is invalid or missing scope")
            results.append({
                "topic": topic,
                "address": address,
                "status": "unauthorized",
                "id": None,
                "message": "401 Unauthorized — check API token and scopes",
            })
            # No point continuing if auth fails
            break

        else:
            logger.warning("Unexpected HTTP %d for topic=%s: %s", status_code, topic, resp_body)
            results.append({
                "topic": topic,
                "address": address,
                "status": f"error_{status_code}",
                "id": None,
                "message": f"HTTP {status_code}: {resp_body}",
            })

        # Small delay between registrations to avoid rate limiting
        time.sleep(0.3)

    logger.info("Webhook registration complete: %d results", len(results))
    return results


def get_registered_webhooks() -> list[dict]:
    """
    Retrieve all currently registered webhooks from Shopify.
    Returns raw list of webhook objects from the API.
    """
    try:
        shop_domain = _get_shop_domain()
        admin_token = _get_admin_token()
    except ValueError as exc:
        logger.error("Configuration error: %s", exc)
        raise

    api_url = _api_base(shop_domain)
    headers = _make_headers(admin_token)

    logger.debug("Fetching registered webhooks from %s", api_url)
    resp = _http_get(api_url, headers)
    webhooks = resp.get("webhooks", [])
    logger.info("Found %d registered webhooks", len(webhooks))
    return webhooks


def ensure_webhooks(base_url: Optional[str] = None) -> list[dict]:
    """
    Convenience function: register all webhooks using the Railway public domain
    or the provided base_url.
    """
    if not base_url:
        railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
        if railway_domain:
            # RAILWAY_PUBLIC_DOMAIN may or may not include the scheme
            if not railway_domain.startswith("http"):
                base_url = f"https://{railway_domain}"
            else:
                base_url = railway_domain
        else:
            base_url = "https://supermegabot-production.up.railway.app"

    logger.info("ensure_webhooks: using base_url=%s", base_url)
    return register_all_webhooks(base_url)


async def run_webhook_registration() -> dict:
    """
    Async wrapper for scheduler integration.
    Returns a summary dict with registration results.
    """
    logger.info("run_webhook_registration: starting async webhook registration")
    try:
        results = ensure_webhooks()
        stats = _compute_stats(results)
        logger.info("run_webhook_registration complete: %s", stats)
        return {"success": True, "results": results, "stats": stats}
    except Exception as exc:
        logger.error("run_webhook_registration failed: %s", exc, exc_info=True)
        return {"success": False, "error": str(exc), "results": [], "stats": {}}


def get_webhook_stats() -> dict:
    """
    Return a stats dict describing registered webhooks vs. expected topics.
    """
    try:
        registered = get_registered_webhooks()
    except Exception as exc:
        logger.error("get_webhook_stats: could not fetch webhooks: %s", exc)
        return {
            "error": str(exc),
            "total_registered": 0,
            "expected_topics": len(WEBHOOK_TOPICS),
            "matched_topics": 0,
            "unmatched_topics": [t for t, _ in WEBHOOK_TOPICS],
            "extra_webhooks": 0,
        }

    registered_topics = {wh.get("topic") for wh in registered}
    expected_topics = {topic for topic, _ in WEBHOOK_TOPICS}

    matched = expected_topics & registered_topics
    missing = expected_topics - registered_topics
    extra = registered_topics - expected_topics

    stats = {
        "total_registered": len(registered),
        "expected_topics": len(WEBHOOK_TOPICS),
        "matched_topics": len(matched),
        "missing_topics": sorted(missing),
        "extra_topic_count": len(extra),
        "all_present": len(missing) == 0,
        "webhooks": [
            {"id": wh.get("id"), "topic": wh.get("topic"), "address": wh.get("address")}
            for wh in registered
        ],
    }
    logger.info("Webhook stats: matched=%d/%d missing=%s",
                len(matched), len(expected_topics), sorted(missing))
    return stats


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_stats(results: list[dict]) -> dict:
    counts = {"registered": 0, "already_exists": 0, "error": 0, "unauthorized": 0}
    for r in results:
        status = r.get("status", "error")
        if status == "registered":
            counts["registered"] += 1
        elif status == "already_exists":
            counts["already_exists"] += 1
        elif status == "unauthorized":
            counts["unauthorized"] += 1
        else:
            counts["error"] += 1
    counts["total"] = len(results)
    return counts


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    result = asyncio.run(run_webhook_registration())
    print(json.dumps(result, indent=2))
