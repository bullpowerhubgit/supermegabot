#!/usr/bin/env python3
"""MegaBot AI-Wrapper Nischen-SaaS — Auto-Launch + Promotion."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("AIWrapper")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
STATE_FILE = DATA_DIR / "ai_wrappers.json"

NICHES: List[Dict[str, Any]] = [
    {
        "id": "handwerker-angebote",
        "name": "AI-Handwerker-Angebote-Generator",
        "price_eur": 59,
        "prompt": (
            "Erstelle ein professionelles Handwerker-Angebot für {kunde} in {ort}. "
            "Leistung: {leistung}. Preisrahmen: {preis} EUR. Ton: seriös, klar, DACH."
        ),
        "landing_hook": "Angebote in 60 Sekunden — für Maler, Elektriker, SHK.",
    },
    {
        "id": "immobilien-expose",
        "name": "AI-Immobilien-Exposé-Generator",
        "price_eur": 79,
        "prompt": (
            "Schreibe ein verkaufsstarkes Immobilien-Exposé für {objekt} in {ort}. "
            "Fläche: {qm} m². Preis: {preis} EUR. Zielgruppe: Käufer/Mieter DACH."
        ),
        "landing_hook": "Exposés die Makler sofort versenden können.",
    },
    {
        "id": "steuerberater-texte",
        "name": "AI-Steuerberater-Texte",
        "price_eur": 69,
        "prompt": (
            "Formuliere einen Mandanten-Brief für Steuerberater: Thema {thema}, "
            "Frist {frist}, Ton sachlich-vertrauensvoll, DACH-Rechtshinweis."
        ),
        "landing_hook": "Mandantenkommunikation schneller und konsistent.",
    },
]


class AIWrapperEngine:
    def __init__(self):
        self.state = self._load()

    def _load(self) -> Dict[str, Any]:
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"wrappers": [], "promotions": [], "launched_at": None}

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(self.state, indent=2, ensure_ascii=False), encoding="utf-8")

    def auto_launch_wrappers(self, *, force: bool = False) -> List[Dict[str, Any]]:
        """Startet fehlende Nischen-Wrapper (idempotent)."""
        existing = {w["id"] for w in self.state.get("wrappers", [])}
        launched: List[Dict[str, Any]] = []
        for n in NICHES:
            if n["id"] in existing and not force:
                continue
            wrapper = {
                **n,
                "status": "live",
                "created_at": datetime.now().isoformat(),
                "checkout_hint": f"€{n['price_eur']}/Mo — Stripe/DS24 Checkout verknüpfen",
            }
            self.state.setdefault("wrappers", []).append(wrapper)
            launched.append(wrapper)
            log.info("AI-Wrapper live: %s (€%s)", wrapper["name"], wrapper["price_eur"])
        if launched:
            self.state["launched_at"] = datetime.now().isoformat()
            self._save()
        return launched

    async def promote_wrappers(self) -> Dict[str, Any]:
        """Promotion über DS24 + Telegram (echte Kanäle)."""
        wrappers = self.state.get("wrappers") or self.auto_launch_wrappers()
        if not wrappers:
            wrappers = self.auto_launch_wrappers()

        posts = 0
        errors: List[str] = []

        for w in wrappers[:3]:
            text = (
                f"🤖 {w['name']} — {w['landing_hook']}\n"
                f"Ab €{w['price_eur']}/Monat · ShopText.ai / MegaBot"
            )
            try:
                from modules.notify_hub import async_send_telegram
                await async_send_telegram(text)
                posts += 1
            except Exception as e:
                errors.append(str(e)[:80])

        try:
            from modules.ds24_affiliate_blaster import blast_niche
            r = await blast_niche("AI SaaS")
            if r.get("ok") or r.get("blasted", 0) > 0:
                posts += int(r.get("blasted", 1))
        except Exception as e:
            errors.append(f"ds24:{e}"[:80])

        promo = {
            "timestamp": datetime.now().isoformat(),
            "wrappers": len(wrappers),
            "posts": posts,
            "errors": errors,
        }
        self.state.setdefault("promotions", []).append(promo)
        self._save()
        return {"ok": posts > 0, **promo}

    def get_status(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "wrappers_live": len(self.state.get("wrappers", [])),
            "wrappers": self.state.get("wrappers", []),
            "last_promotion": (self.state.get("promotions") or [None])[-1],
            "niches_available": len(NICHES),
        }


async def run_ai_wrapper_cycle() -> Dict[str, Any]:
    eng = AIWrapperEngine()
    launched = eng.auto_launch_wrappers()
    promo = await eng.promote_wrappers()
    return {"ok": True, "launched": len(launched), "promotion": promo, "status": eng.get_status()}