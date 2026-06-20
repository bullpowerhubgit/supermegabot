"""
AI Content Calendar — KI-gesteuerte tägliche Content-Planung für alle Kanäle.
Generiert 7-Tage-Kalender mit viralen Posts für DACH E-Commerce Zielgruppe.
"""
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp

log = logging.getLogger("ContentCalendar")

_CALENDAR_FILE = Path("/tmp/bullpower_content_calendar.json")

CONTENT_TYPES = [
    "educational_tip",
    "case_study",
    "product_demo",
    "trend_alert",
    "promotional",
    "engagement",
    "behind_scenes",
]

CHANNELS = ["telegram", "instagram", "facebook", "linkedin", "shopify_blog"]


async def generate_daily_calendar(days: int = 7) -> dict:
    """Erstellt KI-generierten Content-Plan für die nächsten `days` Tage."""
    from modules.ai_client import ai_complete
    today = datetime.now()
    calendar = []

    for offset in range(days):
            day = today + timedelta(days=offset)
            ctype = CONTENT_TYPES[offset % len(CONTENT_TYPES)]
            prompt = (
                f"Du bist ein viraler E-Commerce Marketing-Experte (DACH).\n"
                f"Erstelle für {day.strftime('%A, %d. %B %Y')} einen {ctype} Post:\n"
                "- Thema: Shopify / eCommerce KI-Automatisierung\n"
                "- Zielgruppe: Deutschsprachige Online-Shop-Betreiber\n"
                "- Antworte NUR mit gültigem JSON mit diesen Keys:\n"
                '  {"title":"...", "caption":"...(120 Wörter)...", '
                '"hashtags":["tag1",...20 tags], "cta":"...", "image_prompt":"..."}'
            )
            try:
                raw = await ai_complete(prompt, max_tokens=700)
                # Strip markdown fences if present
                raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
                content = json.loads(raw)
            except Exception as exc:
                content = {
                    "title": f"{ctype} — {day.strftime('%d.%m')}",
                    "caption": f"Automatischer Content für {day.strftime('%d.%m.%Y')}",
                    "hashtags": ["#Shopify", "#eCommerce", "#KI", "#Automatisierung"],
                    "cta": "Jetzt starten →",
                    "image_prompt": "E-Commerce automation futuristic",
                    "_error": str(exc)[:100],
                }

            calendar.append({
                "date": day.strftime("%Y-%m-%d"),
                "day": day.strftime("%A"),
                "type": ctype,
                "content": content,
                "channels": CHANNELS,
                "posted": False,
            })

    result = {"generated_at": today.isoformat(), "calendar": calendar}
    try:
        _CALENDAR_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception:
        pass

    log.info("Content calendar generated: %d days", len(calendar))
    first = calendar[0] if calendar else {}
    return {"days": len(calendar), "first_day": first, "file": str(_CALENDAR_FILE)}


async def get_todays_content() -> dict:
    """Holt den Content für heute. Generiert neu wenn nicht vorhanden."""
    today = datetime.now().strftime("%Y-%m-%d")
    if _CALENDAR_FILE.exists():
        try:
            data = json.loads(_CALENDAR_FILE.read_text())
            for entry in data.get("calendar", []):
                if entry.get("date") == today:
                    return entry
        except Exception:
            pass
    await generate_daily_calendar()
    # Try once more after generation
    try:
        data = json.loads(_CALENDAR_FILE.read_text())
        for entry in data.get("calendar", []):
            if entry.get("date") == today:
                return entry
    except Exception:
        pass
    return {"date": today, "content": {"title": "Fallback", "caption": "eCommerce automatisieren"}}


async def mark_posted(date: str, channel: str) -> None:
    """Markiert einen Eintrag als gepostet."""
    if not _CALENDAR_FILE.exists():
        return
    try:
        data = json.loads(_CALENDAR_FILE.read_text())
        for entry in data.get("calendar", []):
            if entry.get("date") == date:
                posted = entry.get("posted_channels", [])
                if channel not in posted:
                    posted.append(channel)
                entry["posted_channels"] = posted
                entry["posted"] = len(posted) >= len(CHANNELS)
        _CALENDAR_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        pass
