#!/usr/bin/env python3
"""
BPI SYS-06: Platform Migration Rush Monitor
Überwacht Social-Media-Plattform-Krisen und bereitet Emergency-Kits vor.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
log = logging.getLogger("MigrationRush")

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")

PLATFORMS = {
    "tiktok":    {"name": "TikTok",    "url": "https://www.tiktok.com",    "kit": 49, "svc": 299},
    "twitter_x": {"name": "Twitter/X", "url": "https://x.com",             "kit": 49, "svc": 299},
    "instagram": {"name": "Instagram", "url": "https://www.instagram.com", "kit": 49, "svc": 199},
    "youtube":   {"name": "YouTube",   "url": "https://www.youtube.com",   "kit": 49, "svc": 299},
}

CRISIS_HIGH   = 8
CRISIS_LAUNCH = 15


class MigrationRush:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.state_file = Path(__file__).parent.parent / "data" / "migration_rush_state.json"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> dict:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception:
                pass
        return {"platforms": {}, "active_crises": [], "kits_launched": [], "last_check": ""}

    def _save_state(self, state: dict):
        self.state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    async def _check_platform(self, key: str, cfg: dict) -> dict:
        result = {"platform": key, "name": cfg["name"], "status": "unknown", "crisis_score": 0}
        try:
            import time
            t0 = time.time()
            async with self.session.get(
                cfg["url"],
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": "Mozilla/5.0 SuperMegaBot/1.0"},
                allow_redirects=True,
            ) as resp:
                result["reachable"]   = resp.status < 500
                result["response_ms"] = int((time.time() - t0) * 1000)
                result["http_status"] = resp.status
                result["status"]      = "online" if resp.status < 500 else "DOWN"
                result["crisis_score"] = 20 if resp.status >= 500 else 0
        except asyncio.TimeoutError:
            result["status"]       = "timeout"
            result["crisis_score"] = 15
        except Exception as e:
            result["status"]       = f"error"
            result["crisis_score"] = 5
            log.debug("Platform check error %s: %s", key, e)
        return result

    async def monitor_platforms(self) -> dict:
        state  = self._load_state()
        now    = datetime.now(timezone.utc).isoformat()
        checks = await asyncio.gather(*[self._check_platform(k, v) for k, v in PLATFORMS.items()])

        crises = []
        alerts = []
        for check in checks:
            pk    = check["platform"]
            score = check.get("crisis_score", 0)
            check["total_crisis_score"] = score
            state["platforms"][pk]      = check

            if score >= CRISIS_HIGH:
                crises.append(pk)
                cfg = PLATFORMS[pk]
                alerts.append(
                    f"🚨 {cfg['name']} KRISE! Score {score} → "
                    f"Emergency Kit €{cfg['kit']} + Migration-Service €{cfg['svc']}"
                )
                if score >= CRISIS_LAUNCH and pk not in state.get("kits_launched", []):
                    await self._alert_kit_launch(pk, cfg)
                    state.setdefault("kits_launched", []).append(pk)

        state["active_crises"] = crises
        state["last_check"]    = now
        self._save_state(state)

        online = sum(1 for c in checks if c.get("status") == "online")
        if alerts:
            await self._send_tg("\n".join(alerts))

        return {
            "checked":       len(checks),
            "online":        online,
            "crises":        len(crises),
            "active_crises": crises,
            "timestamp":     now,
        }

    async def _alert_kit_launch(self, pk: str, cfg: dict):
        msg = (
            f"⚡ SOFORT-AKTION: {cfg['name']} Krise!\n"
            f"Emergency Kit €{cfg['kit']} auf DS24 aktivieren → Produkt 669750\n"
            f"Migration-Service €{cfg['svc']} als Upsell · Zeitfenster: 48h!"
        )
        await self._send_tg(msg)

    async def _send_tg(self, msg: str):
        if not TG_TOKEN or not TG_CHAT:
            return
        try:
            async with self.session.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as _:
                pass
        except Exception:
            pass

    async def get_status(self) -> dict:
        state = self._load_state()
        return {
            "platforms_monitored": len(PLATFORMS),
            "active_crises":       state.get("active_crises", []),
            "kits_launched":       state.get("kits_launched", []),
            "last_check":          state.get("last_check", "nie"),
        }


async def monitor_all_platforms() -> dict:
    async with aiohttp.ClientSession() as session:
        return await MigrationRush(session).monitor_platforms()


async def get_status() -> dict:
    async with aiohttp.ClientSession() as session:
        return await MigrationRush(session).get_status()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(asyncio.run(monitor_all_platforms()), indent=2))
