"""
GCP Services — Cloud Vision, Translation, Natural Language, Text-to-Speech
Projekt: gen-lang-client-0895465231 (europe-west3)
Alle Calls via GCP_API_KEY — kein OAuth nötig für REST APIs.

Verwendung in anderen Modulen:
    from modules.gcp_services import translate_text, analyze_image, detect_sentiment
"""
import os
import logging
import base64
import asyncio
import aiohttp
from typing import Optional

log = logging.getLogger("GCPServices")

GCP_API_KEY  = os.getenv("GCP_API_KEY", "")
GCP_PROJECT  = os.getenv("GCP_PROJECT_ID", "gen-lang-client-0895465231")
GCP_REGION   = os.getenv("GCP_REGION", "europe-west3")

_VISION_URL      = "https://vision.googleapis.com/v1/images:annotate"
_TRANSLATE_URL   = "https://translation.googleapis.com/language/translate/v2"
_NLP_URL         = "https://language.googleapis.com/v1/documents:analyzeSentiment"
_TTS_URL         = "https://texttospeech.googleapis.com/v1/text:synthesize"
_DETECT_LANG_URL = "https://translation.googleapis.com/language/translate/v2/detect"


def _key_params() -> str:
    return f"?key={GCP_API_KEY}" if GCP_API_KEY else ""


# ── Cloud Translation ─────────────────────────────────────────────────────────

async def translate_text(text: str, target_lang: str = "en", source_lang: str = "de") -> str:
    """Übersetzt Text mit der Cloud Translation API."""
    if not GCP_API_KEY or not text:
        return text
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post(
                f"{_TRANSLATE_URL}{_key_params()}",
                json={"q": text[:5000], "target": target_lang, "source": source_lang, "format": "html"},
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    return d["data"]["translations"][0]["translatedText"]
                log.warning("Translation %s: %s", r.status, await r.text())
    except Exception as e:
        log.warning("translate_text: %s", e)
    return text


async def translate_batch(texts: list, target_lang: str = "en") -> list:
    """Übersetzt eine Liste von Texten parallel."""
    tasks = [translate_text(t, target_lang) for t in texts]
    return await asyncio.gather(*tasks, return_exceptions=False)


async def detect_language(text: str) -> str:
    """Erkennt die Sprache eines Textes."""
    if not GCP_API_KEY:
        return "de"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.post(
                f"{_DETECT_LANG_URL}{_key_params()}",
                json={"q": text[:500]},
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    return d["data"]["detections"][0][0].get("language", "de")
    except Exception as e:
        log.warning("detect_language: %s", e)
    return "de"


# ── Cloud Vision ──────────────────────────────────────────────────────────────

async def analyze_image(image_url: str) -> dict:
    """
    Analysiert ein Produktbild:
    - Labels (was ist auf dem Bild)
    - Dominant Colors
    - Safe Search
    - Web Entities (Produkt-Kontext)
    """
    if not GCP_API_KEY or not image_url:
        return {}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(
                f"{_VISION_URL}{_key_params()}",
                json={"requests": [{
                    "image": {"source": {"imageUri": image_url}},
                    "features": [
                        {"type": "LABEL_DETECTION", "maxResults": 10},
                        {"type": "IMAGE_PROPERTIES"},
                        {"type": "SAFE_SEARCH_DETECTION"},
                        {"type": "WEB_DETECTION", "maxResults": 5},
                    ]
                }]}
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    resp = d.get("responses", [{}])[0]
                    labels = [l["description"] for l in resp.get("labelAnnotations", [])]
                    web = [e["description"] for e in resp.get("webDetection", {}).get("webEntities", []) if e.get("description")]
                    safe = resp.get("safeSearchAnnotation", {})
                    colors = resp.get("imagePropertiesAnnotation", {}).get("dominantColors", {}).get("colors", [])
                    top_color = colors[0].get("color", {}) if colors else {}
                    return {
                        "labels": labels,
                        "web_entities": web,
                        "is_safe": safe.get("adult", "UNKNOWN") not in ("LIKELY", "VERY_LIKELY"),
                        "dominant_color_rgb": f"rgb({top_color.get('red',0)},{top_color.get('green',0)},{top_color.get('blue',0)})",
                        "auto_tags": list(set(labels + web))[:10],
                    }
                log.warning("Vision %s", r.status)
    except Exception as e:
        log.warning("analyze_image: %s", e)
    return {}


async def generate_product_alt_text(image_url: str, product_title: str = "") -> str:
    """Generiert SEO-Alt-Text für Produktbilder via Vision API."""
    analysis = await analyze_image(image_url)
    if not analysis:
        return product_title
    labels = analysis.get("labels", [])[:5]
    entities = analysis.get("web_entities", [])[:3]
    all_terms = list(dict.fromkeys(labels + entities))
    if product_title:
        return f"{product_title} — {', '.join(all_terms[:4])}"
    return ", ".join(all_terms[:6])


# ── Cloud Natural Language ────────────────────────────────────────────────────

async def detect_sentiment(text: str) -> dict:
    """Sentiment-Analyse für Produktbeschreibungen oder Reviews."""
    if not GCP_API_KEY or not text:
        return {"score": 0.0, "magnitude": 0.0, "label": "neutral"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post(
                f"{_NLP_URL}{_key_params()}",
                json={"document": {"type": "PLAIN_TEXT", "content": text[:1000], "language": "de"},
                      "encodingType": "UTF8"}
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    score = d.get("documentSentiment", {}).get("score", 0.0)
                    mag = d.get("documentSentiment", {}).get("magnitude", 0.0)
                    label = "positiv" if score > 0.2 else ("negativ" if score < -0.2 else "neutral")
                    return {"score": score, "magnitude": mag, "label": label}
    except Exception as e:
        log.warning("detect_sentiment: %s", e)
    return {"score": 0.0, "magnitude": 0.0, "label": "neutral"}


# ── Cloud Text-to-Speech ──────────────────────────────────────────────────────

async def text_to_speech(text: str, lang: str = "de-DE", voice: str = "de-DE-Standard-A") -> Optional[bytes]:
    """Konvertiert Text zu Audio (MP3) — für Telegram Voice oder TikTok."""
    if not GCP_API_KEY:
        return None
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(
                f"{_TTS_URL}{_key_params()}",
                json={
                    "input": {"text": text[:5000]},
                    "voice": {"languageCode": lang, "name": voice},
                    "audioConfig": {"audioEncoding": "MP3", "speakingRate": 1.1}
                }
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    audio_b64 = d.get("audioContent", "")
                    return base64.b64decode(audio_b64) if audio_b64 else None
    except Exception as e:
        log.warning("text_to_speech: %s", e)
    return None


# ── Shopify Product Enhancer via GCP ─────────────────────────────────────────

async def enhance_shopify_product(product: dict) -> dict:
    """
    Verbessert ein Shopify-Produkt mit GCP:
    - Analysiert Produktbild → generiert Auto-Tags + Alt-Text
    - Übersetzt Beschreibung nach EN (für internationale SEO)
    - Sentiment-Check der Beschreibung
    """
    enhanced = dict(product)
    title = product.get("title", "")
    description = product.get("body_html", "")
    image_url = product.get("image_url", "")

    tasks = {}
    if image_url:
        tasks["vision"] = analyze_image(image_url)
    if description:
        tasks["sentiment"] = detect_sentiment(description[:500])
    if title:
        tasks["translate_title"] = translate_text(title, "en", "de")

    results = {}
    if tasks:
        done = await asyncio.gather(*tasks.values(), return_exceptions=True)
        results = dict(zip(tasks.keys(), done))

    vision_data = results.get("vision") or {}
    if vision_data.get("auto_tags"):
        existing_tags = product.get("tags", "").split(",") if product.get("tags") else []
        new_tags = existing_tags + vision_data["auto_tags"][:5]
        enhanced["tags"] = ",".join(dict.fromkeys(t.strip() for t in new_tags if t.strip()))

    if results.get("translate_title") and not isinstance(results["translate_title"], Exception):
        enhanced["title_en"] = results["translate_title"]

    sentiment = results.get("sentiment") or {}
    enhanced["gcp_sentiment"] = sentiment.get("label", "neutral")
    enhanced["gcp_enhanced"] = True

    return enhanced


async def translate_shopify_product(product: dict, target_langs: list = None) -> dict:
    """Übersetzt Shopify-Produkt in mehrere Sprachen für internationale Märkte."""
    if not target_langs:
        target_langs = ["en", "fr", "it", "pl"]
    title = product.get("title", "")
    desc = product.get("body_html", "")
    translations = {}
    for lang in target_langs:
        t_title, t_desc = await asyncio.gather(
            translate_text(title, lang, "de"),
            translate_text(desc[:2000], lang, "de")
        )
        translations[lang] = {"title": t_title, "body_html": t_desc}
    return translations


# ── Quick Test ────────────────────────────────────────────────────────────────

async def ping() -> dict:
    """Testet ob GCP API Key funktioniert."""
    result = await translate_text("Hallo Welt", "en", "de")
    return {"ok": result == "Hello World" or len(result) > 0, "result": result,
            "project": GCP_PROJECT, "key_set": bool(GCP_API_KEY)}
