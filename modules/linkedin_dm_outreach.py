"""
LinkedIn DM Outreach — vollautomatischer B2B Kaltakquise via LinkedIn API
=========================================================================
Sendet täglich bis zu 50 Connection Requests + Follow-up DMs an DACH
E-Commerce Entscheider. Rate-Limit-konform (20/h, 50/Tag).

Nutzung:
    from modules.linkedin_dm_outreach import run_daily_outreach, get_stats
    result = await run_daily_outreach(limit=50)
"""
from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from pathlib import Path

import aiohttp

log = logging.getLogger("LinkedInDM")

# ── Konfiguration ─────────────────────────────────────────────────────────────
_TOKEN      = lambda: os.getenv("LINKEDIN_ACCESS_TOKEN", "")
_PERSON_URN = lambda: os.getenv("LINKEDIN_PERSON_URN", "urn:li:person:YcxbqVN0ZR")
_STRIPE_LINK = "https://buy.stripe.com/7sYeVf53k5PQ7EA2Wq4F203"
_API = "https://api.linkedin.com/v2"
_DB  = Path(__file__).parent.parent / "data" / "linkedin_dm.db"

DAILY_LIMIT   = 50
HOURLY_LIMIT  = 20
FOLLOWUP_DAYS = 3   # Tage nach Connection-Annahme → Follow-up DM senden

# ── Templates ─────────────────────────────────────────────────────────────────
_CONNECTION_NOTE = (
    "Hallo {first_name}, ich baue Shopify-Automatisierungen für DACH-Shops "
    "— spart 10h/Woche. Würde mich über Austausch freuen! Rudolf"
)  # max 300 Zeichen

_FOLLOWUP_DM = (
    "Hallo {first_name}, danke für die Verbindung! 🙏\n\n"
    "Ich helfe Online-Shops wie deinem, Bestellungen, Preise und Marketing "
    "vollautomatisch zu managen — ohne Agentur, ohne Aufwand.\n\n"
    "Kurze Demo gewünscht? → {stripe_link}\n\nBeste Grüße, Rudolf"
)

# ── Branchen-Targets für DACH E-Commerce ─────────────────────────────────────
TARGET_KEYWORDS = [
    "Shopify", "E-Commerce", "Onlineshop", "Online Shop",
    "WooCommerce", "Dropshipping", "Amazon FBA", "Fulfillment",
    "Einzelhandel Digital", "D2C", "Direct to Consumer",
]
TARGET_TITLES = [
    "Geschäftsführer", "Inhaber", "CEO", "Founder", "Gründer",
    "Head of E-Commerce", "E-Commerce Manager", "Online Marketing",
]
TARGET_LOCATIONS = ["Deutschland", "Österreich", "Schweiz", "Germany", "Austria"]


# ── Datenbank ─────────────────────────────────────────────────────────────────
def _db() -> sqlite3.Connection:
    _DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sent_requests (
            profile_urn   TEXT PRIMARY KEY,
            first_name    TEXT,
            headline      TEXT,
            sent_at       REAL,
            status        TEXT DEFAULT 'pending',
            connected_at  REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS conversations (
            conversation_urn TEXT PRIMARY KEY,
            profile_urn      TEXT,
            first_name       TEXT,
            dm_sent_at       REAL DEFAULT 0,
            replied          INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS daily_counts (
            date_str  TEXT PRIMARY KEY,
            requests  INTEGER DEFAULT 0,
            dms       INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    return conn


def _today() -> str:
    from datetime import date
    return date.today().isoformat()


def _requests_today(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT requests FROM daily_counts WHERE date_str=?", (_today(),)
    ).fetchone()
    return row["requests"] if row else 0


def _inc_counter(conn: sqlite3.Connection, field: str) -> None:
    conn.execute(
        f"""INSERT INTO daily_counts (date_str, {field})
            VALUES (?, 1)
            ON CONFLICT(date_str) DO UPDATE SET {field}={field}+1""",
        (_today(),),
    )
    conn.commit()


def _already_sent(conn: sqlite3.Connection, profile_urn: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sent_requests WHERE profile_urn=?", (profile_urn,)
    ).fetchone() is not None


# ── LinkedIn API helpers ──────────────────────────────────────────────────────
def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_TOKEN()}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }


async def _get(session: aiohttp.ClientSession, path: str, params: dict | None = None) -> dict:
    url = f"{_API}{path}"
    async with session.get(url, headers=_headers(), params=params or {},
                           timeout=aiohttp.ClientTimeout(total=15)) as r:
        if r.status == 429:
            raise RateLimitError("LinkedIn rate limit hit")
        if r.status == 403:
            raise PermissionError(f"LinkedIn 403 on {path}")
        return await r.json(content_type=None)


async def _post(session: aiohttp.ClientSession, path: str, payload: dict) -> tuple[int, dict]:
    url = f"{_API}{path}"
    async with session.post(url, headers=_headers(), json=payload,
                            timeout=aiohttp.ClientTimeout(total=15)) as r:
        if r.status == 429:
            raise RateLimitError("LinkedIn rate limit hit")
        try:
            body = await r.json(content_type=None)
        except Exception:
            body = {}
        return r.status, body


class RateLimitError(Exception):
    pass


# ── Kernfunktionen ────────────────────────────────────────────────────────────

async def search_decision_makers(
    industry: str = "E-Commerce",
    location: str = "Deutschland",
    limit: int = 20,
) -> list[dict]:
    """
    Sucht DACH E-Commerce Entscheider via LinkedIn People Search.
    Gibt Liste mit {urn, first_name, last_name, headline} zurück.

    Hinweis: LinkedIn /v2/search erfordert Marketing-API-Zugang.
    Fallback: Suche über /v2/connections (eigenes Netzwerk durchgehen).
    """
    token = _TOKEN()
    if not token:
        log.warning("LINKEDIN_ACCESS_TOKEN nicht gesetzt")
        return []

    profiles = []
    async with aiohttp.ClientSession() as session:
        # Primär: People Search (benötigt r_organization_social oder Sales Navigator)
        try:
            data = await _get(session, "/search/blended", {
                "q": "people",
                "query": (
                    f"(and (eq field=industryV2 (li:standardIndustry:68)) "
                    f"keywords:{industry})"
                ),
                "start": 0,
                "count": limit,
            })
            elements = data.get("elements", [])
            for el in elements:
                entity = el.get("image", {})
                urn = el.get("trackingUrn", "")
                if urn:
                    profiles.append({
                        "urn": urn,
                        "first_name": el.get("title", {}).get("text", ""),
                        "headline": el.get("primarySubtitle", {}).get("text", ""),
                    })
        except Exception as e:
            log.debug("Search API nicht verfügbar (%s) — nutze Connections-Fallback", e)

        # Fallback: eigene Connections als Outreach-Quelle
        if not profiles:
            try:
                data = await _get(session, "/connections", {
                    "q": "viewer",
                    "start": 0,
                    "count": limit,
                    "fields": "id,firstName,lastName,headline,profilePicture",
                })
                for el in data.get("elements", []):
                    urn = f"urn:li:person:{el.get('id','')}"
                    profiles.append({
                        "urn": urn,
                        "first_name": el.get("firstName", {}).get("localized", {}).get("de_DE", "")
                                   or el.get("firstName", {}).get("localized", {}).get("en_US", "")
                                   or "Hallo",
                        "headline": el.get("headline", ""),
                    })
            except Exception as e:
                log.debug("Connections Fallback fehlgeschlagen: %s", e)

    log.info("search_decision_makers: %d Profile gefunden (industry=%s, loc=%s)",
             len(profiles), industry, location)
    return profiles


async def send_connection_request(profile_urn: str, first_name: str = "") -> bool:
    """Sendet Verbindungsanfrage mit personalisierter Notiz."""
    token = _TOKEN()
    if not token:
        return False

    note = _CONNECTION_NOTE.format(first_name=first_name or "zusammen")
    # LinkedIn begrenzt Connection Note auf 300 Zeichen
    note = note[:300]

    payload = {
        "invitee": {
            "com.linkedin.voyager.growth.invitation.InviteeProfile": {
                "profileId": profile_urn.split(":")[-1],
            }
        },
        "message": note,
    }

    async with aiohttp.ClientSession() as session:
        try:
            status, body = await _post(session, "/growth/normInvitations", payload)
            if status in (200, 201):
                log.info("Connection Request gesendet → %s (%s)", profile_urn, first_name)
                return True
            else:
                log.debug("Connection Request %d: %s", status, str(body)[:100])
                # 409 = bereits verbunden oder Request pending — trotzdem ok
                return status == 409
        except RateLimitError:
            log.warning("Rate Limit — warte 60s")
            await asyncio.sleep(60)
            return False
        except PermissionError as e:
            log.warning("Permission: %s", e)
            return False
        except Exception as e:
            log.debug("Connection Request Fehler: %s", e)
            return False


async def send_dm(conversation_urn: str, message: str) -> bool:
    """Sendet Direktnachricht an bestehende Verbindung."""
    token = _TOKEN()
    if not token:
        return False

    payload = {
        "eventCreate": {
            "value": {
                "com.linkedin.voyager.messaging.create.MessageCreate": {
                    "attributedBody": {
                        "text": message,
                        "attributes": [],
                    },
                    "attachments": [],
                }
            }
        },
        "deduplicationId": str(int(time.time())),
    }

    async with aiohttp.ClientSession() as session:
        try:
            encoded_urn = conversation_urn.replace(":", "%3A")
            status, body = await _post(
                session,
                f"/messaging/conversations/{encoded_urn}/events",
                payload,
            )
            success = status in (200, 201, 202)
            if success:
                log.info("DM gesendet → %s", conversation_urn)
            else:
                log.debug("DM %d: %s", status, str(body)[:100])
            return success
        except RateLimitError:
            await asyncio.sleep(60)
            return False
        except Exception as e:
            log.debug("DM Fehler: %s", e)
            return False


async def _process_followups(conn: sqlite3.Connection) -> int:
    """Sendet Follow-up DMs an frisch verbundene Kontakte (nach FOLLOWUP_DAYS Tagen)."""
    cutoff = time.time() - (FOLLOWUP_DAYS * 86400)
    due = conn.execute("""
        SELECT sr.profile_urn, sr.first_name, sr.connected_at
        FROM sent_requests sr
        LEFT JOIN conversations c ON c.profile_urn = sr.profile_urn
        WHERE sr.status = 'connected'
          AND sr.connected_at > 0
          AND sr.connected_at <= ?
          AND (c.dm_sent_at IS NULL OR c.dm_sent_at = 0)
        LIMIT 10
    """, (cutoff,)).fetchall()

    sent = 0
    for row in due:
        first_name = row["first_name"] or "zusammen"
        message = _FOLLOWUP_DM.format(first_name=first_name, stripe_link=_STRIPE_LINK)

        # Conversation URN ableiten (vereinfacht: direkter Messaging-Versuch)
        conversation_urn = f"urn:li:msgConversation:(urn:li:person:{_PERSON_URN().split(':')[-1]},{row['profile_urn'].split(':')[-1]})"
        ok = await send_dm(conversation_urn, message)
        if ok:
            conn.execute("""
                INSERT INTO conversations (conversation_urn, profile_urn, first_name, dm_sent_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(conversation_urn) DO UPDATE SET dm_sent_at=excluded.dm_sent_at
            """, (conversation_urn, row["profile_urn"], first_name, time.time()))
            conn.commit()
            _inc_counter(conn, "dms")
            sent += 1
            await asyncio.sleep(5)  # Anti-Spam-Pause

    return sent


async def run_daily_outreach(limit: int = DAILY_LIMIT) -> dict:
    """
    Hauptfunktion: läuft täglich via Scheduler.
    1. Prüft Tageslimit (50 Requests/Tag)
    2. Sucht neue DACH E-Commerce Entscheider
    3. Sendet Connection Requests mit personalisierter Notiz
    4. Sendet Follow-up DMs an frisch verbundene Kontakte
    """
    if not _TOKEN():
        return {"error": "LINKEDIN_ACCESS_TOKEN nicht gesetzt", "sent": 0}

    conn = _db()
    already_sent_today = _requests_today(conn)

    if already_sent_today >= limit:
        conn.close()
        return {"status": "daily_limit_reached", "sent_today": already_sent_today}

    remaining = limit - already_sent_today
    results = {"connection_requests": 0, "followup_dms": 0, "errors": 0}

    # ── Follow-up DMs (Priorität: bereits verbundene zuerst) ──
    try:
        followups = await _process_followups(conn)
        results["followup_dms"] = followups
    except Exception as e:
        log.warning("Follow-up Fehler: %s", e)

    # ── Neue Connection Requests ──
    industries = ["E-Commerce", "Online Handel", "Einzelhandel"]
    locations  = ["Deutschland", "Österreich", "Schweiz"]
    batch_size = min(remaining, HOURLY_LIMIT)

    for industry in industries:
        if results["connection_requests"] >= batch_size:
            break
        for location in locations:
            if results["connection_requests"] >= batch_size:
                break

            profiles = await search_decision_makers(industry, location, limit=20)

            for profile in profiles:
                if results["connection_requests"] >= batch_size:
                    break

                urn = profile.get("urn", "")
                if not urn or _already_sent(conn, urn):
                    continue

                first_name = profile.get("first_name", "")
                ok = await send_connection_request(urn, first_name)

                if ok:
                    conn.execute("""
                        INSERT OR IGNORE INTO sent_requests
                          (profile_urn, first_name, headline, sent_at, status)
                        VALUES (?, ?, ?, ?, 'pending')
                    """, (urn, first_name, profile.get("headline", ""), time.time()))
                    conn.commit()
                    _inc_counter(conn, "requests")
                    results["connection_requests"] += 1
                    # Pause zwischen Requests: Anti-Spam
                    await asyncio.sleep(8)
                else:
                    results["errors"] += 1

    conn.close()
    log.info("LinkedIn Outreach: %d Connection Requests, %d Follow-up DMs gesendet",
             results["connection_requests"], results["followup_dms"])
    return {
        "status": "done",
        **results,
        "total_today": already_sent_today + results["connection_requests"],
    }


def get_stats() -> dict:
    """Statistiken aus linkedin_dm.db für Dashboard."""
    conn = _db()
    total_requests = conn.execute("SELECT COUNT(*) FROM sent_requests").fetchone()[0]
    connected = conn.execute(
        "SELECT COUNT(*) FROM sent_requests WHERE status='connected'"
    ).fetchone()[0]
    dms_sent = conn.execute(
        "SELECT COUNT(*) FROM conversations WHERE dm_sent_at > 0"
    ).fetchone()[0]
    replied = conn.execute(
        "SELECT COUNT(*) FROM conversations WHERE replied=1"
    ).fetchone()[0]
    today = conn.execute(
        "SELECT requests, dms FROM daily_counts WHERE date_str=?", (_today(),)
    ).fetchone()
    conn.close()
    return {
        "total_requests_sent": total_requests,
        "connections_accepted": connected,
        "dms_sent": dms_sent,
        "replies_received": replied,
        "today_requests": today["requests"] if today else 0,
        "today_dms": today["dms"] if today else 0,
        "acceptance_rate": f"{round(connected/max(total_requests,1)*100,1)}%",
    }
