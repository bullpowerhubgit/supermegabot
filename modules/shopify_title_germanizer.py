"""
Shopify Title Germanizer — Übersetzt englische Produkttitel auf Deutsch
Verarbeitet aktive Produkte in Batches, speichert Fortschritt lokal.
Ziel: Alle 19k Produkte mit deutschen Titeln für bessere Konversion + SEO
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import aiohttp

log = logging.getLogger("TitleGermanizer")

SHOP_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOP_TOKEN  = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-10")

DATA_DIR    = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
STATE_FILE  = DATA_DIR / "title_germanizer.json"

_GERMAN_INDICATORS = [
    "und", "mit", "für", "das", "der", "die", "von", "zu", "ein", "ist",
    "auf", "oder", "aus", "bei", "nach", "über", "wie", "auch", "als",
    "nicht", "sich", "Produkt", "Zubehör", "Gerät", "Kabel", "Ladegerät",
]


def _is_english(title: str) -> bool:
    lower = title.lower()
    if any(w in lower for w in _GERMAN_INDICATORS):
        return False
    return True


def _base() -> str:
    return f"https://{SHOP_DOMAIN}/admin/api/{API_VERSION}"


def _hdrs() -> dict:
    return {"X-Shopify-Access-Token": SHOP_TOKEN, "Content-Type": "application/json"}


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"translated": 0, "last_id": 0, "processed_ids": []}


def _save_state(s: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Keep only last 5000 processed IDs to avoid state file bloat
    if len(s.get("processed_ids", [])) > 5000:
        s["processed_ids"] = s["processed_ids"][-5000:]
    STATE_FILE.write_text(json.dumps(s, default=str))


async def _translate_batch(titles: list[str]) -> list[str]:
    """Übersetzt eine Liste von Titeln auf einmal via AI (billiger als einzelne Calls)."""
    if not titles:
        return []
    try:
        from modules.ai_client import ai_complete
        numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
        prompt = f"""Übersetze diese Shopify-Produkttitel ins Deutsche. Regeln:
- Behalte Markennamen, Modellnummern, technische Abkürzungen (WiFi, USB, BMS, V, W, mAh, IP65, etc.) UNVERÄNDERT
- "Smart" kann auf Deutsch bleiben
- Übersetze nur die beschreibenden Teile
- Erhalte die Zeichenanzahl ähnlich (±20 Zeichen)
- Gib NUR die nummerierten übersetzten Titel zurück, KEIN anderer Text

{numbered}"""
        raw = await ai_complete(prompt, max_tokens=len(titles) * 30)
        if not raw:
            return titles  # Fallback: Original behalten

        lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
        result = []
        for line in lines:
            # Entferne Nummerierung (z.B. "1. ", "1) ")
            if len(line) > 2 and line[0].isdigit():
                if line[1] in '.):' or (len(line) > 3 and line[1:3] in '. '):
                    line = line.lstrip('0123456789').lstrip('.').lstrip(')').lstrip(':').strip()
            result.append(line)

        # Sicherheit: gleiche Anzahl zurückgeben
        if len(result) == len(titles):
            return result
        return titles  # Fallback wenn Anzahl nicht stimmt
    except Exception as e:
        log.warning("_translate_batch: %s", e)
        return titles  # Fallback: Original


async def run_translation_batch(max_per_run: int = 50) -> dict:
    """
    Übersetzt bis zu max_per_run englische Produkttitel auf Deutsch.
    Restart-safe: speichert Fortschritt in state file.
    """
    if not SHOP_DOMAIN or not SHOP_TOKEN:
        return {"ok": False, "error": "Shopify credentials fehlen"}

    state = _load_state()
    processed_ids = set(state.get("processed_ids", []))
    last_id = state.get("last_id", 0)
    total_translated = state.get("translated", 0)

    translated_this_run = 0
    errors = 0

    async with aiohttp.ClientSession() as s:
        # Fetch active products, start from last_id
        all_products = []
        fetch_id = last_id

        for _ in range(3):  # Max 3 Fetch-Pages pro Run
            try:
                async with s.get(
                    f"{_base()}/products.json",
                    headers=_hdrs(),
                    params={"status": "active", "limit": 50, "since_id": fetch_id,
                            "fields": "id,title,product_type"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    if r.status == 429:
                        await asyncio.sleep(10)
                        continue
                    if r.status != 200:
                        break
                    batch = (await r.json()).get("products", [])
                    if not batch:
                        break
                    all_products.extend(batch)
                    fetch_id = batch[-1]["id"]
                    if len(batch) < 50 or len(all_products) >= max_per_run * 2:
                        break
            except Exception as e:
                log.warning("fetch: %s", e)
                break

        # Filter: nur englische Titel, noch nicht verarbeitet
        to_translate = [
            p for p in all_products
            if str(p["id"]) not in processed_ids and _is_english(p.get("title", ""))
        ][:max_per_run]

        if not to_translate:
            log.info("Germanizer: Keine englischen Titel zum Übersetzen gefunden")
            return {"ok": True, "translated_this_run": 0, "total_translated": total_translated,
                    "msg": "Keine englischen Titel in diesem Batch"}

        # In 10er-Gruppen übersetzen (effizienter)
        chunk_size = 10
        for chunk_start in range(0, len(to_translate), chunk_size):
            chunk = to_translate[chunk_start:chunk_start + chunk_size]
            titles = [p.get("title", "") for p in chunk]

            german_titles = await _translate_batch(titles)

            for p, german_title in zip(chunk, german_titles):
                pid = p["id"]
                if not german_title or german_title == p.get("title", ""):
                    processed_ids.add(str(pid))
                    continue

                # Titel kürzen auf max 255 Zeichen (Shopify-Limit)
                german_title = german_title[:255]

                try:
                    async with s.put(
                        f"{_base()}/products/{pid}.json",
                        headers=_hdrs(),
                        json={"product": {"id": pid, "title": german_title}},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as r2:
                        if r2.status == 429:
                            await asyncio.sleep(10)
                            # Nochmal versuchen
                            async with s.put(
                                f"{_base()}/products/{pid}.json",
                                headers=_hdrs(),
                                json={"product": {"id": pid, "title": german_title}},
                                timeout=aiohttp.ClientTimeout(total=10),
                            ) as r3:
                                ok = r3.status in (200, 201)
                        elif r2.status in (200, 201):
                            ok = True
                        else:
                            ok = False
                            errors += 1

                    if ok:
                        translated_this_run += 1
                        processed_ids.add(str(pid))
                        log.info("Germanized: %s → %s", p.get("title", "")[:40], german_title[:40])
                except Exception as e:
                    log.warning("update %s: %s", pid, e)
                    errors += 1

                await asyncio.sleep(0.7)  # Rate limit

            await asyncio.sleep(1)

    # State speichern
    new_last_id = to_translate[-1]["id"] if to_translate else last_id
    state.update({
        "translated": total_translated + translated_this_run,
        "last_id": new_last_id,
        "processed_ids": list(processed_ids),
        "last_run": datetime.utcnow().isoformat(),
    })
    _save_state(state)

    return {
        "ok": True,
        "translated_this_run": translated_this_run,
        "total_translated": total_translated + translated_this_run,
        "errors": errors,
        "processed_total": len(processed_ids),
    }


async def get_status() -> dict:
    state = _load_state()
    return {
        "ok": True,
        "module": "Shopify Title Germanizer",
        "translated": state.get("translated", 0),
        "processed_ids": len(state.get("processed_ids", [])),
        "last_run": state.get("last_run", None),
    }
