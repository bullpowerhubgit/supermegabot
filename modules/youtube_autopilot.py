#!/usr/bin/env python3
"""
YouTube Autopilot — Erstellt Produkt-Showcase-Videos & postet automatisch.

Pipeline:
  1. Echte Shopify-Produkte holen
  2. KI-Script generieren (Deutsch)
  3. Voiceover via OpenAI TTS
  4. Video-Frames via Pillow (Slides)
  5. FFmpeg: Frames + Audio → MP4
  6. YouTube Data API v3: Upload
  7. SQLite: History & Stats
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import re
import subprocess
import tempfile
import textwrap
import time
import urllib.request
import urllib.parse
from pathlib import Path

import aiohttp

from modules.ai_client import ai_complete

log = logging.getLogger("YouTubeAutopilot")

# ─── Konfiguration ────────────────────────────────────────────────────────────
YT_API_KEY        = os.getenv("YOUTUBE_API_KEY", "")
YT_CHANNEL_ID     = os.getenv("YOUTUBE_CHANNEL_ID", "")
YT_CLIENT_ID      = os.getenv("YOUTUBE_CLIENT_ID", "")
YT_CLIENT_SECRET  = os.getenv("YOUTUBE_CLIENT_SECRET", "")
YT_REFRESH_TOKEN  = os.getenv("YOUTUBE_REFRESH_TOKEN", "")
YT_SA_CREDS       = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials/yt-tracker-sa.json")

OPENAI_KEY        = os.getenv("OPENAI_API_KEY", "")
SHOPIFY_DOMAIN    = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN     = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VERSION   = os.getenv("SHOPIFY_API_VERSION", "2024-10")
SHOP_STORE_URL    = os.getenv("SHOPIFY_STORE_URL", "https://ineedit.com.co")

DB_PATH           = Path("data/youtube_autopilot.db")
TEMP_DIR          = Path("data/yt_temp")
OUT_DIR           = Path("data/yt_videos")

# Video-Dimensionen (YouTube HD)
VW, VH = 1920, 1080
FPS     = 24

# Farbpalette (Dark Mode — professionell)
C_BG         = (15, 15, 20)
C_CARD       = (25, 28, 40)
C_ACCENT     = (99, 102, 241)     # Indigo
C_ACCENT2    = (244, 63, 94)      # Rose
C_WHITE      = (255, 255, 255)
C_GRAY       = (160, 163, 190)
C_PRICE      = (52, 211, 153)     # Emerald


# ─── Datenbank ────────────────────────────────────────────────────────────────
def _db():
    import sqlite3
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    con.execute("""
        CREATE TABLE IF NOT EXISTS yt_videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT,
            title TEXT,
            product_id TEXT,
            product_title TEXT,
            video_path TEXT,
            status TEXT DEFAULT 'created',
            views INTEGER DEFAULT 0,
            created_at INTEGER DEFAULT (strftime('%s','now')),
            uploaded_at INTEGER
        )
    """)
    con.commit()
    return con


# ─── Shopify: Produkt holen ───────────────────────────────────────────────────
async def _get_random_product() -> dict | None:
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        log.warning("Shopify nicht konfiguriert")
        return None
    url = f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}/products.json?limit=5&status=active"
    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                log.warning("Shopify Fehler: %s", r.status)
                return None
            data = await r.json()
    products = data.get("products", [])
    if not products:
        return None
    import random
    p = random.choice(products)
    images = p.get("images", [])
    variants = p.get("variants", [])
    price = variants[0].get("price", "0") if variants else "0"
    img_url = images[0].get("src", "") if images else ""
    return {
        "id": str(p["id"]),
        "title": p.get("title", ""),
        "body_html": p.get("body_html", ""),
        "price": price,
        "image_url": img_url,
        "handle": p.get("handle", ""),
        "tags": p.get("tags", ""),
        "vendor": p.get("vendor", ""),
    }


async def _download_image(url: str) -> bytes | None:
    if not url:
        return None
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=20), ssl=False) as r:
                if r.status == 200:
                    return await r.read()
    except Exception as e:
        log.warning("Bild-Download fehlgeschlagen: %s", e)
    return None


# ─── KI: Script generieren ────────────────────────────────────────────────────
async def _generate_script(product: dict) -> str:
    title   = product["title"]
    price   = product["price"]
    body    = re.sub(r"<[^>]+>", " ", product.get("body_html", ""))[:400]
    prompt  = f"""Du bist ein professioneller YouTube-Sprecher für einen deutschen Tech-Shop.
Erstelle ein 60-Sekunden-Video-Script (ca. 150 Wörter) für dieses Produkt:

Produkt: {title}
Preis: €{price}
Beschreibung: {body}

Das Script soll:
- Mit einer starken Hook beginnen ("Kennst du das Problem...")
- 3 Hauptvorteile nennen
- Mit einem klaren CTA enden ("Jetzt auf ineedit.com.co bestellen — Link in der Bio!")
- Natürlich und begeistert klingen (nicht übertrieben)
- Auf Deutsch sein
- KEIN Intro wie "Hallo liebe Zuschauer" verwenden
- Direkt mit dem Thema starten

Gib NUR den Sprechtext zurück, keine Formatierung, keine Anmerkungen."""

    # KI-Script via ai_complete (automatischer Provider-Fallback)
    try:
        text = await ai_complete(prompt, system="", max_tokens=400)
        if text:
            return text.strip()
    except Exception as e:
        log.warning("ai_complete Script-Gen Fehler: %s", e)

    # Fallback: Einfaches Template
    return (
        f"Dieses Produkt wird dein Leben verändern! "
        f"Der {title} ist das, was du schon lange gesucht hast. "
        f"Mit modernster Technologie ausgestattet bietet er dir drei entscheidende Vorteile: "
        f"erstklassige Qualität, einfache Bedienung und ein unschlagbares Preis-Leistungs-Verhältnis. "
        f"Für nur {price} Euro gehört dieses Highlight sofort dir. "
        f"Kein Warten mehr — bestell jetzt auf ineedit punkt com punkt co und sichere dir dein Exemplar!"
    )


# ─── OpenAI TTS: Voiceover ────────────────────────────────────────────────────
async def _generate_voiceover(script: str, out_path: Path) -> bool:
    if not OPENAI_KEY:
        log.warning("OPENAI_API_KEY fehlt — kein Voiceover")
        return False
    try:
        req_data = json.dumps({
            "model": "tts-1",
            "input": script,
            "voice": "onyx",
            "speed": 0.95,
        }).encode()
        req = urllib.request.Request(
            "https://api.openai.com/v1/audio/speech",
            data=req_data,
            headers={
                "Authorization": f"Bearer {OPENAI_KEY}",
                "Content-Type": "application/json",
            }
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            audio_data = r.read()
        out_path.write_bytes(audio_data)
        log.info("Voiceover erstellt: %s (%d bytes)", out_path.name, len(audio_data))
        return True
    except Exception as e:
        log.error("TTS Fehler: %s", e)
        return False


# ─── Pillow: Video-Frames erstellen ──────────────────────────────────────────
def _make_frames(product: dict, img_data: bytes | None, frames_dir: Path, num_frames: int) -> int:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        log.error("Pillow nicht installiert: pip3 install pillow")
        return 0

    frames_dir.mkdir(parents=True, exist_ok=True)

    # Font laden (System-Fonts)
    def _font(size: int):
        for fp in [
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]:
            if Path(fp).exists():
                try:
                    return ImageFont.truetype(fp, size)
                except Exception:
                    pass
        return ImageFont.load_default()

    title   = product["title"]
    price   = product["price"]
    store   = "ineedit.com.co"
    vendor  = product.get("vendor", "")

    frames_per_slide = num_frames // 5  # 5 Slides total

    slide_func = [
        lambda: _slide_intro(title, price, vendor),
        lambda: _slide_product(title, img_data),
        lambda: _slide_features(product),
        lambda: _slide_cta(price, store),
        lambda: _slide_outro(store),
    ]

    frame_idx = 0
    for s_idx, make_slide in enumerate(slide_func):
        img = make_slide()
        for _ in range(frames_per_slide):
            img.save(frames_dir / f"frame_{frame_idx:05d}.jpg", quality=90)
            frame_idx += 1

    # Restliche Frames mit letztem Slide füllen
    last = slide_func[-1]()
    while frame_idx < num_frames:
        last.save(frames_dir / f"frame_{frame_idx:05d}.jpg", quality=90)
        frame_idx += 1

    return frame_idx


def _base_img():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (VW, VH), C_BG)
    d   = ImageDraw.Draw(img)
    # Hintergrund-Gradient simulieren (Streifen)
    for y in range(0, VH, 4):
        alpha = int(8 * (1 - y / VH))
        d.line([(0, y), (VW, y)], fill=(C_ACCENT[0], C_ACCENT[1], C_ACCENT[2]))
    return img, d


def _draw_text_wrapped(d, text: str, font, xy, max_width: int, fill, line_spacing: int = 10):
    from PIL import ImageFont
    x, y = xy
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        try:
            bbox = font.getbbox(test)
            w = bbox[2] - bbox[0]
        except Exception:
            w = len(test) * 12
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    for line in lines:
        d.text((x, y), line, font=font, fill=fill)
        try:
            bbox = font.getbbox(line)
            h = bbox[3] - bbox[1]
        except Exception:
            h = 30
        y += h + line_spacing
    return y


def _slide_intro(title: str, price: str, vendor: str):
    from PIL import Image, ImageDraw, ImageFont

    def _font(size):
        for fp in [
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]:
            if Path(fp).exists():
                try:
                    return ImageFont.truetype(fp, size)
                except Exception:
                    pass
        return ImageFont.load_default()

    img = Image.new("RGB", (VW, VH), C_BG)
    d   = ImageDraw.Draw(img)

    # Accent-Balken links
    d.rectangle([(0, 0), (12, VH)], fill=C_ACCENT)

    # Gradient-Hintergrund rechte Seite (hell)
    for x in range(VW // 2, VW):
        alpha = int(15 * (x - VW // 2) / (VW // 2))
        d.line([(x, 0), (x, VH)], fill=(alpha, alpha, alpha + 20))

    # Vendor-Tag
    d.rectangle([(80, 80), (80 + len(vendor) * 18 + 40, 130)], fill=C_ACCENT)
    d.text((100, 87), vendor.upper() or "INEEDIT.COM.CO", font=_font(26), fill=C_WHITE)

    # Haupttitel
    _draw_text_wrapped(d, title, _font(72), (80, 180), VW - 200, C_WHITE, line_spacing=15)

    # Preis-Badge
    d.ellipse([(VW - 300, VH - 320), (VW - 30, VH - 70)], fill=C_ACCENT2)
    d.text((VW - 230, VH - 240), f"€{price}", font=_font(90), fill=C_WHITE)
    d.text((VW - 200, VH - 130), "JETZT KAUFEN", font=_font(28), fill=C_WHITE)

    # Bottom bar
    d.rectangle([(0, VH - 60), (VW, VH)], fill=C_CARD)
    d.text((80, VH - 45), "ineedit.com.co", font=_font(30), fill=C_ACCENT)
    d.text((VW - 500, VH - 45), "Smart Home & Tech", font=_font(30), fill=C_GRAY)

    return img


def _slide_product(title: str, img_data: bytes | None):
    from PIL import Image, ImageDraw, ImageFont

    def _font(size):
        for fp in [
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]:
            if Path(fp).exists():
                try:
                    return ImageFont.truetype(fp, size)
                except Exception:
                    pass
        return ImageFont.load_default()

    img = Image.new("RGB", (VW, VH), C_BG)
    d   = ImageDraw.Draw(img)

    if img_data:
        try:
            prod_img = Image.open(io.BytesIO(img_data)).convert("RGB")
            # Fit-to-box 860x860 zentriert links
            prod_img.thumbnail((860, 860), Image.LANCZOS)
            offset_x = (VW // 2 - prod_img.width) // 2
            offset_y = (VH - prod_img.height) // 2
            img.paste(prod_img, (offset_x, offset_y))
        except Exception:
            pass

    # Rechte Seite: Titel + Info
    d.text((VW // 2 + 60, 120), title[:40] + ("…" if len(title) > 40 else ""),
           font=_font(52), fill=C_WHITE)
    d.text((VW // 2 + 60, 220), "✓ Sofort lieferbar", font=_font(36), fill=C_PRICE)
    d.text((VW // 2 + 60, 280), "✓ Kostenloser Versand ab €50", font=_font(36), fill=C_PRICE)
    d.text((VW // 2 + 60, 340), "✓ 30 Tage Rückgaberecht", font=_font(36), fill=C_PRICE)
    d.text((VW // 2 + 60, 440), "Nur bei ineedit.com.co", font=_font(40), fill=C_GRAY)

    d.rectangle([(0, VH - 8), (VW, VH)], fill=C_ACCENT)
    return img


def _slide_features(product: dict):
    from PIL import Image, ImageDraw, ImageFont

    def _font(size):
        for fp in ["/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
            if Path(fp).exists():
                try:
                    return ImageFont.truetype(fp, size)
                except Exception:
                    pass
        return ImageFont.load_default()

    img = Image.new("RGB", (VW, VH), C_BG)
    d   = ImageDraw.Draw(img)

    tags = [t.strip() for t in product.get("tags", "").split(",") if t.strip()][:6]
    if not tags:
        tags = ["Hochwertige Qualität", "Moderne Technologie", "Einfache Bedienung",
                "Langlebig", "Top-Bewertungen", "Bestes Preis-Leistungs-Verhältnis"]

    d.text((80, 80), "PRODUKTVORTEILE", font=_font(40), fill=C_ACCENT)
    d.rectangle([(80, 135), (900, 140)], fill=C_ACCENT)

    for i, tag in enumerate(tags[:6]):
        y  = 180 + i * 130
        x  = 80 if i % 2 == 0 else VW // 2 + 40
        if i % 2 != 0:
            y = 180 + (i - 1) * 130 // 2 + (i // 2) * 130
        d.rectangle([(x, y), (x + 800, y + 100)], fill=C_CARD)
        d.rectangle([(x, y), (x + 8, y + 100)], fill=C_ACCENT)
        d.text((x + 30, y + 28), f"✦ {tag[:45]}", font=_font(34), fill=C_WHITE)

    d.rectangle([(0, VH - 60), (VW, VH)], fill=C_CARD)
    d.text((VW // 2 - 200, VH - 45), "ineedit.com.co — Smart Home & Tech", font=_font(28), fill=C_GRAY)
    return img


def _slide_cta(price: str, store: str):
    from PIL import Image, ImageDraw, ImageFont

    def _font(size):
        for fp in ["/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
            if Path(fp).exists():
                try:
                    return ImageFont.truetype(fp, size)
                except Exception:
                    pass
        return ImageFont.load_default()

    img = Image.new("RGB", (VW, VH), C_BG)
    d   = ImageDraw.Draw(img)

    # Großer Accent-Kreis im Hintergrund
    d.ellipse([(VW // 2 - 700, -300), (VW // 2 + 700, VH + 300)], fill=(20, 22, 35))

    d.text((80, 100), "EXKLUSIVES ANGEBOT", font=_font(48), fill=C_ACCENT)
    d.rectangle([(80, 162), (700, 167)], fill=C_ACCENT2)

    d.text((80, 220), "Nur für kurze Zeit:", font=_font(52), fill=C_GRAY)
    d.text((80, 320), f"€{price}", font=_font(160), fill=C_PRICE)

    d.rectangle([(80, 520), (880, 640)], fill=C_ACCENT2)
    d.text((160, 548), "JETZT BESTELLEN →", font=_font(56), fill=C_WHITE)

    d.text((80, 680), store, font=_font(52), fill=C_WHITE)
    d.text((80, 760), "Link in der Bio & Beschreibung!", font=_font(44), fill=C_GRAY)
    d.text((80, 840), "Kostenloser Versand · 30 Tage Rückgabe", font=_font(36), fill=C_GRAY)

    d.rectangle([(VW - 400, 80), (VW - 40, 200)], fill=C_CARD)
    d.text((VW - 370, 100), "💳 Sicheres", font=_font(30), fill=C_WHITE)
    d.text((VW - 370, 143), "   Bezahlen", font=_font(30), fill=C_WHITE)

    return img


def _slide_outro(store: str):
    from PIL import Image, ImageDraw, ImageFont

    def _font(size):
        for fp in ["/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
            if Path(fp).exists():
                try:
                    return ImageFont.truetype(fp, size)
                except Exception:
                    pass
        return ImageFont.load_default()

    img = Image.new("RGB", (VW, VH), C_BG)
    d   = ImageDraw.Draw(img)

    for y in range(0, VH, 80):
        d.rectangle([(0, y), (VW, y + 2)], fill=(25, 27, 40))

    d.text((VW // 2 - 400, 180), "GEFÄLLT DIR?", font=_font(100), fill=C_WHITE)
    d.text((VW // 2 - 520, 320), "👍 LIKEN  🔔 ABONNIEREN  💬 KOMMENTIEREN", font=_font(44), fill=C_ACCENT)

    d.rectangle([(VW // 2 - 480, 460), (VW // 2 + 480, 580)], fill=C_ACCENT2)
    d.text((VW // 2 - 380, 485), f"🛒 SHOP: {store}", font=_font(54), fill=C_WHITE)

    d.text((VW // 2 - 300, 640), "Mehr Videos jeden Tag!", font=_font(48), fill=C_GRAY)
    d.text((VW // 2 - 240, 740), "Smart Home · Tech · Gadgets", font=_font(40), fill=C_GRAY)

    return img


# ─── FFmpeg: Frames + Audio → MP4 ────────────────────────────────────────────
def _create_video(frames_dir: Path, audio_path: Path | None, out_path: Path) -> bool:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = "ffmpeg"

    if audio_path and audio_path.exists():
        # Mit Audio
        cmd = [
            ffmpeg, "-y",
            "-framerate", str(FPS),
            "-i", str(frames_dir / "frame_%05d.jpg"),
            "-i", str(audio_path),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(out_path),
        ]
    else:
        # Nur Video (60 Sekunden)
        cmd = [
            ffmpeg, "-y",
            "-framerate", str(FPS),
            "-i", str(frames_dir / "frame_%05d.jpg"),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-t", "60",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(out_path),
        ]

    result = subprocess.run(cmd, capture_output=True, timeout=300)
    if result.returncode != 0:
        log.error("FFmpeg Fehler: %s", result.stderr.decode()[-500:])
        return False
    log.info("Video erstellt: %s (%.1f MB)", out_path.name, out_path.stat().st_size / 1_048_576)
    return True


# ─── YouTube OAuth2: Access Token ────────────────────────────────────────────
def _get_access_token() -> str | None:
    if not YT_CLIENT_ID or not YT_CLIENT_SECRET or not YT_REFRESH_TOKEN:
        log.warning("YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN fehlen — kein Upload möglich")
        return None
    try:
        data = urllib.parse.urlencode({
            "client_id": YT_CLIENT_ID,
            "client_secret": YT_CLIENT_SECRET,
            "refresh_token": YT_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        }).encode()
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
        token = resp.get("access_token")
        if not token:
            log.error("Token-Refresh fehlgeschlagen: %s", resp)
        return token
    except Exception as e:
        log.error("OAuth2 Refresh Fehler: %s", e)
        return None


def _upload_to_youtube(video_path: Path, title: str, description: str, tags: list) -> str | None:
    access_token = _get_access_token()
    if not access_token:
        log.warning("Kein YouTube Access Token — Upload übersprungen")
        return None

    # Metadata
    metadata = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:500],
            "categoryId": "26",  # How-to & Style
            "defaultLanguage": "de",
            "defaultAudioLanguage": "de",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        }
    }

    # Initialer Upload-Request (resumable)
    meta_bytes = json.dumps(metadata).encode()
    video_size  = video_path.stat().st_size
    init_req = urllib.request.Request(
        f"https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        data=meta_bytes,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(video_size),
        }
    )

    try:
        with urllib.request.urlopen(init_req, timeout=30) as r:
            upload_url = r.headers.get("Location")
        if not upload_url:
            log.error("Kein Upload-URL erhalten")
            return None
    except Exception as e:
        log.error("YouTube Upload-Init Fehler: %s", e)
        return None

    # Datei hochladen (single PUT für Dateien < 256 MB)
    try:
        video_data = video_path.read_bytes()
        put_req = urllib.request.Request(
            upload_url,
            data=video_data,
            method="PUT",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "video/mp4",
                "Content-Length": str(video_size),
            }
        )
        with urllib.request.urlopen(put_req, timeout=300) as r:
            resp = json.loads(r.read())
        video_id = resp.get("id")
        if video_id:
            log.info("✅ YouTube Video hochgeladen: https://youtu.be/%s", video_id)
            return video_id
        log.error("Upload-Response ohne Video-ID: %s", resp)
        return None
    except Exception as e:
        log.error("YouTube Upload Fehler: %s", e)
        return None


def _send_telegram_notification(message: str):
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


# ─── Haupt-Pipeline ──────────────────────────────────────────────────────────
async def create_and_upload_video() -> dict:
    result = {"status": "error", "video_id": None, "video_path": None}

    # 1. Shopify-Produkt
    log.info("Hole Shopify-Produkt...")
    product = await _get_random_product()
    if not product:
        result["error"] = "Kein Shopify-Produkt gefunden"
        return result

    log.info("Produkt: %s (€%s)", product["title"], product["price"])

    # 2. Script generieren
    log.info("Generiere Script...")
    script = await _generate_script(product)

    # 3. Verzeichnisse vorbereiten
    ts     = int(time.time())
    work   = TEMP_DIR / str(ts)
    work.mkdir(parents=True, exist_ok=True)
    frames_dir  = work / "frames"
    audio_path  = work / "voiceover.mp3"
    video_path  = OUT_DIR / f"video_{ts}_{product['id']}.mp4"

    # 4. Voiceover
    log.info("Generiere Voiceover...")
    has_audio = await _generate_voiceover(script, audio_path)

    # 5. Frames erstellen
    log.info("Erstelle Video-Frames...")
    audio_duration = 60  # Default 60s
    if has_audio and audio_path.exists():
        # Audio-Länge via ffprobe
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(audio_path)],
                capture_output=True, timeout=10
            )
            info = json.loads(r.stdout)
            audio_duration = max(30, min(120, float(info.get("format", {}).get("duration", 60))))
        except Exception:
            pass

    num_frames = int(audio_duration * FPS)
    img_data = await _download_image(product["image_url"])
    made = _make_frames(product, img_data, frames_dir, num_frames)
    if made == 0:
        result["error"] = "Frame-Erstellung fehlgeschlagen"
        return result

    # 6. Video zusammenbauen
    log.info("Erstelle MP4 mit FFmpeg...")
    if not _create_video(frames_dir, audio_path if has_audio else None, video_path):
        result["error"] = "FFmpeg Video-Erstellung fehlgeschlagen"
        return result

    result["video_path"] = str(video_path)

    # 7. YouTube-Metadaten
    yt_title = f"{product['title']} — Jetzt bei ineedit.com.co | Smart Home & Tech"[:100]
    yt_desc  = (
        f"🛒 Jetzt kaufen: {SHOP_STORE_URL}/products/{product.get('handle','')}\n\n"
        f"{script}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ {product['title']}\n"
        f"💶 Nur €{product['price']}\n"
        f"🚚 Kostenloser Versand ab €50\n"
        f"🔄 30 Tage Rückgaberecht\n\n"
        f"📌 Shop: {SHOP_STORE_URL}\n"
        f"📌 Weitere Produkte: {SHOP_STORE_URL}/collections\n\n"
        f"#SmartHome #TechGadgets #ineedit #Shopify #OnlineShopping #DeutscherShop"
    )
    yt_tags = [
        product["title"][:50], "Smart Home", "Tech Gadgets", "Online Shopping",
        "ineedit", "Günstiger kaufen", "Produkttest", "Empfehlung", "Deutsch",
    ]
    tags_from_prod = [t.strip() for t in product.get("tags", "").split(",") if t.strip()]
    yt_tags.extend(tags_from_prod[:10])

    # 8. DB speichern (vor Upload)
    con = _db()
    con.execute(
        "INSERT INTO yt_videos (title, product_id, product_title, video_path, status) VALUES (?,?,?,?,?)",
        (yt_title, product["id"], product["title"], str(video_path), "created")
    )
    db_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    con.commit()

    # 9. YouTube-Upload
    log.info("Lade auf YouTube hoch...")
    video_id = _upload_to_youtube(video_path, yt_title, yt_desc, yt_tags)

    if video_id:
        con.execute(
            "UPDATE yt_videos SET video_id=?, status='uploaded', uploaded_at=strftime('%s','now') WHERE id=?",
            (video_id, db_id)
        )
        con.commit()
        result["status"]   = "uploaded"
        result["video_id"] = video_id
        result["url"]      = f"https://youtu.be/{video_id}"
        _send_telegram_notification(
            f"🎥 <b>YouTube Video live!</b>\n"
            f"📦 {product['title']}\n"
            f"🔗 <a href='https://youtu.be/{video_id}'>youtu.be/{video_id}</a>"
        )
    else:
        result["status"] = "created_no_upload"
        result["note"]   = "Video erstellt — YouTube-Upload benötigt YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN"
        log.info("Video erstellt aber nicht hochgeladen (kein OAuth2 Token): %s", video_path)

    # 10. Temp-Dateien aufräumen
    try:
        import shutil
        shutil.rmtree(work, ignore_errors=True)
    except Exception:
        pass

    result["product"]    = product["title"]
    result["video_path"] = str(video_path)
    con.close()
    return result


async def get_youtube_stats() -> dict:
    con = _db()
    total     = con.execute("SELECT COUNT(*) FROM yt_videos").fetchone()[0]
    uploaded  = con.execute("SELECT COUNT(*) FROM yt_videos WHERE status='uploaded'").fetchone()[0]
    recent    = con.execute(
        "SELECT title, status, video_id, created_at FROM yt_videos ORDER BY created_at DESC LIMIT 5"
    ).fetchall()
    con.close()
    return {
        "total_created": total,
        "uploaded_to_youtube": uploaded,
        "has_oauth": bool(YT_REFRESH_TOKEN),
        "channel_id": YT_CHANNEL_ID,
        "recent": [
            {"title": r[0], "status": r[1], "video_id": r[2], "ts": r[3]}
            for r in recent
        ],
    }


# ─── OAuth2 Setup Helper ──────────────────────────────────────────────────────
def print_oauth_setup_instructions():
    """Druckt Anleitung für einmaligen YouTube OAuth2 Setup."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║         YouTube OAuth2 — Einmaliger Setup                    ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1. Gehe zu: https://console.cloud.google.com/              ║
║  2. Projekt "yt-tracker-478101" öffnen                       ║
║  3. APIs → OAuth 2.0 Client IDs → Neu erstellen             ║
║     Typ: Desktop App                                         ║
║  4. YOUTUBE_CLIENT_ID + YOUTUBE_CLIENT_SECRET in .env        ║
║                                                              ║
║  Dann dieses Script ausführen:                               ║
║  python3 -c "from modules.youtube_autopilot import           ║
║              run_oauth_flow; run_oauth_flow()"               ║
╚══════════════════════════════════════════════════════════════╝
""")


def run_oauth_flow():
    """Interaktiver OAuth2-Flow für einmaligen Setup."""
    if not YT_CLIENT_ID or not YT_CLIENT_SECRET:
        print_oauth_setup_instructions()
        return

    scope = "https://www.googleapis.com/auth/youtube.upload"
    auth_url = (
        f"https://accounts.google.com/o/oauth2/auth"
        f"?client_id={YT_CLIENT_ID}"
        f"&redirect_uri=urn:ietf:wg:oauth:2.0:oob"
        f"&response_type=code"
        f"&scope={urllib.parse.quote(scope)}"
        f"&access_type=offline"
        f"&prompt=consent"
    )
    print(f"\n1. Öffne diesen Link:\n{auth_url}\n")
    code = input("2. Code eingeben: ").strip()

    data = urllib.parse.urlencode({
        "client_id": YT_CLIENT_ID,
        "client_secret": YT_CLIENT_SECRET,
        "code": code,
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
        "grant_type": "authorization_code",
    }).encode()

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    with urllib.request.urlopen(req) as r:
        resp = json.loads(r.read())

    print(f"\n✅ Füge zu .env hinzu:\nYOUTUBE_REFRESH_TOKEN={resp.get('refresh_token')}\n")
