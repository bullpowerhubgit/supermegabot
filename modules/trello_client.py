#!/usr/bin/env python3
"""
Trello Client — Board/Karten-Management + Stripe-Event-Kopplung

ENV:
  TRELLO_API_KEY     — Power-Up Key
  TRELLO_TOKEN       — OAuth Token (read/write)
  TRELLO_BOARD_ID    — Ziel-Board
  TRELLO_LIST_TODAY  — Listen-ID "Heute"
  TRELLO_LIST_WEEK   — Listen-ID "Diese Woche"
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("trello_client")

_BASE = "https://api.trello.com/1"
_TIMEOUT = aiohttp.ClientTimeout(total=20)


def _creds() -> tuple[str, str]:
    key = os.getenv("TRELLO_API_KEY", "")
    token = os.getenv("TRELLO_TOKEN", "")
    if not key or not token:
        raise RuntimeError("TRELLO_API_KEY oder TRELLO_TOKEN nicht gesetzt")
    return key, token


def _qs(**extra) -> dict:
    key, token = _creds()
    return {"key": key, "token": token, **extra}


def _board_id() -> str:
    bid = os.getenv("TRELLO_BOARD_ID", "")
    if not bid:
        raise RuntimeError("TRELLO_BOARD_ID nicht gesetzt")
    return bid


def _default_list() -> str:
    return os.getenv("TRELLO_LIST_TODAY") or os.getenv("TRELLO_LIST_WEEK", "")


# ── Low-level helpers ─────────────────────────────────────────────────────────

async def _get(path: str, params: dict | None = None) -> Any:
    qs = _qs(**(params or {}))
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as s:
        async with s.get(f"{_BASE}{path}", params=qs) as r:
            body = await r.json()
            if r.status >= 400:
                raise RuntimeError(f"Trello GET {path} → HTTP {r.status}: {body}")
            return body


async def _post(path: str, data: dict | None = None) -> Any:
    qs = _qs()
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as s:
        async with s.post(f"{_BASE}{path}", params=qs, json=data or {}) as r:
            body = await r.json()
            if r.status >= 400:
                raise RuntimeError(f"Trello POST {path} → HTTP {r.status}: {body}")
            return body


async def _put(path: str, data: dict | None = None) -> Any:
    qs = _qs()
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as s:
        async with s.put(f"{_BASE}{path}", params=qs, json=data or {}) as r:
            body = await r.json()
            if r.status >= 400:
                raise RuntimeError(f"Trello PUT {path} → HTTP {r.status}: {body}")
            return body


# ── Public API ────────────────────────────────────────────────────────────────

async def verify_credentials() -> dict:
    """Prüft Key+Token gegen /members/me. Gibt Member-Objekt zurück."""
    member = await _get("/members/me", {"fields": "id,username,fullName,confirmed"})
    log.info("Trello auth OK: %s (%s)", member.get("fullName"), member.get("username"))
    return {"ok": True, "member": member}


async def get_board(board_id: str | None = None) -> dict:
    """Holt Board-Metadaten."""
    bid = board_id or _board_id()
    return await _get(f"/boards/{bid}", {"fields": "id,name,url,closed"})


async def get_lists(board_id: str | None = None) -> list[dict]:
    """Alle offenen Listen auf dem Board."""
    bid = board_id or _board_id()
    return await _get(f"/boards/{bid}/lists", {"filter": "open", "fields": "id,name,pos"})


async def create_card(
    name: str,
    *,
    list_id: str | None = None,
    desc: str = "",
    due: str | None = None,
    labels: list[str] | None = None,
) -> dict:
    """
    Erstellt eine Karte auf dem Board.
    list_id defaults auf TRELLO_LIST_TODAY.
    Returns das vollständige Card-Objekt.
    """
    lid = list_id or _default_list()
    if not lid:
        raise RuntimeError("Kein list_id und TRELLO_LIST_TODAY/WEEK nicht gesetzt")

    payload: dict[str, Any] = {"idList": lid, "name": name, "desc": desc}
    if due:
        payload["due"] = due
    if labels:
        payload["idLabels"] = ",".join(labels)

    card = await _post("/cards", payload)
    log.info("Trello card created: %s (id=%s)", card.get("name"), card.get("id"))
    return card


async def update_card(
    card_id: str,
    *,
    name: str | None = None,
    desc: str | None = None,
    due: str | None = None,
    closed: bool | None = None,
    list_id: str | None = None,
) -> dict:
    """Aktualisiert Felder einer bestehenden Karte."""
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if desc is not None:
        payload["desc"] = desc
    if due is not None:
        payload["due"] = due
    if closed is not None:
        payload["closed"] = closed
    if list_id is not None:
        payload["idList"] = list_id

    card = await _put(f"/cards/{card_id}", payload)
    log.info("Trello card updated: %s (id=%s)", card.get("name"), card.get("id"))
    return card


async def add_comment(card_id: str, text: str) -> dict:
    """Fügt einen Kommentar auf einer Karte hinzu."""
    result = await _post(f"/cards/{card_id}/actions/comments", {"text": text})
    log.info("Trello comment added to card %s", card_id)
    return result


async def get_card(card_id: str) -> dict:
    """Liest eine Karte vollständig aus."""
    return await _get(f"/cards/{card_id}")


async def find_card_by_external_id(
    external_id: str,
    board_id: str | None = None,
) -> Optional[dict]:
    """
    Sucht Karte anhand einer externen ID (z.B. Stripe charge_id) in der
    Kartenbeschreibung. Format: ext_id:<external_id>
    Gibt None zurück wenn nicht gefunden.
    """
    bid = board_id or _board_id()
    try:
        cards = await _get(f"/boards/{bid}/cards", {"fields": "id,name,desc"})
    except Exception as e:
        log.warning("find_card_by_external_id: board-scan fehlgeschlagen: %s", e)
        return None

    marker = f"ext_id:{external_id}"
    for card in cards:
        if marker in (card.get("desc") or ""):
            return card
    return None


# ── Stripe-Event-Kopplung ─────────────────────────────────────────────────────

_STRIPE_EVENT_MAP = {
    "payment_intent.succeeded": ("Zahlung erfolgreich", "TRELLO_LIST_TODAY"),
    "payment_intent.payment_failed": ("Zahlung fehlgeschlagen", "TRELLO_LIST_TODAY"),
    "customer.subscription.created": ("Neues Abo", "TRELLO_LIST_TODAY"),
    "customer.subscription.deleted": ("Abo gekündigt", "TRELLO_LIST_WEEK"),
    "charge.succeeded": ("Charge OK", "TRELLO_LIST_TODAY"),
    "charge.refunded": ("Rückerstattung", "TRELLO_LIST_TODAY"),
    "invoice.payment_succeeded": ("Invoice bezahlt", "TRELLO_LIST_WEEK"),
    "invoice.payment_failed": ("Invoice fehlgeschlagen", "TRELLO_LIST_TODAY"),
}


async def handle_stripe_event(event_type: str, event_data: dict) -> Optional[dict]:
    """
    Wird von stripe_automation oder dem Webhook-Handler aufgerufen.
    Erstellt oder aktualisiert eine Trello-Karte für das Stripe-Event.

    Returns das Card-Objekt oder None bei nicht-gemappten Events.
    """
    if event_type not in _STRIPE_EVENT_MAP:
        log.debug("Trello: kein Mapping für Stripe-Event %s", event_type)
        return None

    label, list_env = _STRIPE_EVENT_MAP[event_type]
    list_id = os.getenv(list_env, "") or _default_list()
    obj = event_data.get("object", event_data)

    ext_id = (
        obj.get("id")
        or obj.get("payment_intent")
        or obj.get("invoice")
        or ""
    )
    amount_raw = obj.get("amount") or obj.get("amount_paid") or 0
    amount = round(amount_raw / 100, 2) if amount_raw else 0
    currency = (obj.get("currency") or "eur").upper()
    customer = obj.get("customer") or obj.get("customer_email") or "–"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    existing = await find_card_by_external_id(ext_id) if ext_id else None

    card_name = f"[Stripe] {label} — {amount} {currency}"
    card_desc = (
        f"**Event:** {event_type}\n"
        f"**ID:** {ext_id}\n"
        f"**Betrag:** {amount} {currency}\n"
        f"**Kunde:** {customer}\n"
        f"**Zeitpunkt:** {ts}\n\n"
        f"ext_id:{ext_id}"
    )

    if existing:
        card = await update_card(
            existing["id"],
            name=card_name,
            desc=card_desc,
        )
        await add_comment(
            existing["id"],
            f"Update {ts}: {event_type} — {amount} {currency}",
        )
        log.info("Trello: Karte aktualisiert für Stripe-Event %s", ext_id)
    else:
        card = await create_card(
            name=card_name,
            list_id=list_id,
            desc=card_desc,
        )
        log.info("Trello: neue Karte für Stripe-Event %s", ext_id)

    return card
