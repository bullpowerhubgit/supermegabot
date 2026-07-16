"""
Stripe Client — liest Orders/Charges/Customers aus der Stripe API
und schreibt sie in Supabase.

Benötigte Env-Variablen:
  STRIPE_SECRET_KEY  — sk_live_... oder sk_test_...
  SUPABASE_URL       — https://<ref>.supabase.co
  SUPABASE_ANON_KEY  — anon/service key
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger("stripe_client")

STRIPE_API_BASE = "https://api.stripe.com/v1"


_STRIPE_KEY_NAMES = (
    "STRIPE_SECRET_KEY",              # bullpowersrtkennels@gmail.com — IMMER diese!
    "STRIPE_TEST_SECRET_KEY",
    "STRIPE_API_KEY",
    # STRIPE_SECRET_KEY_AIITEC ENTFERNT — 401, falsches Konto
)


def _stripe_key_candidates() -> list[tuple[str, str]]:
    """Working key first (resolver), then remaining envs for fallback."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    try:
        from modules.stripe_key_resolver import get_working_stripe_key, get_working_stripe_key_name
        wk = get_working_stripe_key()
        if wk:
            out.append((get_working_stripe_key_name() or "STRIPE_SECRET_KEY", wk))
            seen.add(wk)
    except Exception:
        pass
    for name in _STRIPE_KEY_NAMES:
        val = os.getenv(name, "").strip()
        if val and val not in seen:
            seen.add(val)
            out.append((name, val))
    return out


def _stripe_key() -> str:
    try:
        from modules.stripe_key_resolver import get_working_stripe_key
        k = get_working_stripe_key()
        if k:
            return k
    except Exception:
        pass
    for _, val in _stripe_key_candidates():
        return val
    return ""


def _stripe_request(key: str, path: str, params: dict | None = None) -> dict:
    import base64
    from modules.stripe_guards import sanitize_get_params

    url = f"{STRIPE_API_BASE}{path}"
    # Dauerhaft: type aus /prices-Query entfernen
    params = sanitize_get_params(path, params)
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"

    req = urllib.request.Request(url)
    token = base64.b64encode(f"{key}:".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("Stripe-Version", "2024-12-18.acacia")

    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def _stripe_get(path: str, params: dict | None = None) -> dict:
    candidates = _stripe_key_candidates()
    if not candidates:
        raise RuntimeError("STRIPE_SECRET_KEY nicht gesetzt")

    errors: list[str] = []
    for name, key in candidates:
        try:
            return _stripe_request(key, path, params)
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300]
            errors.append(f"{name} HTTP {e.code}: {body}")
            if e.code in (401, 403):
                continue
            raise RuntimeError(f"Stripe HTTP {e.code}: {body}") from e
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            continue

    raise RuntimeError("; ".join(errors[-3:]))


def get_todays_charges() -> list[dict]:
    """Alle Charges von heute (UTC)."""
    today_start = int(
        datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    )
    result = []
    params: dict[str, Any] = {"created[gte]": today_start, "limit": 100}
    while True:
        data = _stripe_get("/charges", params)
        result.extend(data.get("data", []))
        if not data.get("has_more"):
            break
        params["starting_after"] = data["data"][-1]["id"]
    return result


def get_revenue_summary() -> dict:
    """Tages-Umsatz aus Stripe Charges."""
    charges = get_todays_charges()
    successful = [c for c in charges if c.get("status") == "succeeded" and not c.get("refunded")]
    total = sum(c.get("amount", 0) for c in successful)
    currency = successful[0].get("currency", "eur").upper() if successful else "EUR"
    return {
        "source": "stripe",
        "today_revenue": round(total / 100, 2),
        "order_count": len(successful),
        "currency": currency,
        "charges": [
            {
                "id": c["id"],
                "amount": round(c["amount"] / 100, 2),
                "currency": c.get("currency", "eur").upper(),
                "description": c.get("description") or c.get("statement_descriptor") or "",
                "created": datetime.fromtimestamp(c["created"], tz=timezone.utc).isoformat(),
                "customer_email": (c.get("billing_details") or {}).get("email"),
            }
            for c in successful
        ],
    }


def write_to_supabase(summary: dict) -> bool:
    """Schreibt Revenue-Snapshot in Supabase via REST API."""
    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    if not url or not key:
        log.warning("Supabase nicht konfiguriert — kein DB-Write")
        return False

    payload = json.dumps({
        "shop": "stripe",
        "total_orders": summary["order_count"],
        "total_revenue": summary["today_revenue"],
        "currency": summary["currency"],
    }).encode()

    req = urllib.request.Request(
        f"{url}/rest/v1/revenue_snapshots",
        data=payload,
        method="POST",
    )
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=minimal")
    req.add_header("Accept-Profile", "public")
    req.add_header("Content-Profile", "public")

    try:
        with urllib.request.urlopen(req, timeout=10):
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        log.error("Supabase write failed HTTP %s: %s", e.code, body)
        return False
    except Exception as e:
        log.error("Supabase write error: %s", e)
        return False


async def get_revenue_stats() -> dict:
    """
    Async wrapper for get_revenue_summary().
    Returns: {today_revenue, order_count, currency, source, charges}
    Compatible with revenue_aggregator and notify_hub expectations.
    """
    import asyncio as _asyncio
    loop = _asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, get_revenue_summary)
    except Exception as exc:
        log.warning("get_revenue_stats failed: %s", exc)
        return {
            "source": "stripe",
            "today_revenue": 0.0,
            "order_count": 0,
            "currency": "EUR",
            "charges": [],
            "error": str(exc),
        }


def is_configured() -> bool:
    return bool(_stripe_key_candidates())


def stripe_key_status() -> dict:
    """Prüft alle Stripe-Keys — liefert ersten gültigen + Fehler der Live-Keys."""
    live_errors: list[str] = []
    for name, key in _stripe_key_candidates():
        try:
            _stripe_request(key, "/balance")
            mode = "test" if "test" in name.lower() or key.startswith("sk_test_") else "live"
            return {"ok": True, "key_name": name, "mode": mode}
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            if "test" not in name.lower():
                live_errors.append(f"{name}: {body[:120]}")
        except Exception as exc:
            if "test" not in name.lower():
                live_errors.append(f"{name}: {exc}")
    return {"ok": False, "error": "; ".join(live_errors) or "Kein gültiger Stripe-Key"}


if __name__ == "__main__":
    import sys
    from pathlib import Path

    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() not in os.environ:
                    os.environ[k.strip()] = v.strip().strip('"')

    logging.basicConfig(level=logging.INFO)
    try:
        summary = get_revenue_summary()
        print(f"Stripe Umsatz heute: {summary['currency']} {summary['today_revenue']:.2f}")
        print(f"Charges: {summary['order_count']}")
        ok = write_to_supabase(summary)
        print(f"Supabase Write: {'✅' if ok else '⚠️ übersprungen (nicht konfiguriert)'}")
    except Exception as e:
        print(f"Fehler: {e}")
        sys.exit(1)
