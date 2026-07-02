#!/usr/bin/env python3
"""
YouTube Shorts Auto-Upload — Shopify Produkte täglich als kurzes Video-Short.
Erstellt ein 15s Produkt-Slideshow-Video und lädt es als YouTube Short hoch.

Nutzung:
    python3 scripts/youtube_shopify_shorts.py         # einmaliger Upload
    python3 scripts/youtube_shopify_shorts.py --test  # nur Video erstellen, kein Upload
"""
import os, sys, json, random, textwrap, subprocess, tempfile, requests, logging
from pathlib import Path
from urllib.parse import urlencode
from io import BytesIO
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("yt_shorts")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# ── Credentials ──────────────────────────────────────────────────────────────
SHOPIFY_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
SHOP_URL       = "https://ineedit.com.co"
YT_RT          = os.getenv("YOUTUBE_REFRESH_TOKEN", "")
YT_CLIENT_ID   = os.getenv("GOOGLE_CLIENT_ID_AIITEC", "")
YT_CLIENT_SEC  = os.getenv("GOOGLE_CLIENT_SECRET_AIITEC", "")

# ── Video-Einstellungen ───────────────────────────────────────────────────────
W, H   = 1080, 1920   # 9:16 Hochformat für Shorts
FPS    = 30
DUR    = 15           # Sekunden

# ── Farben (AiiteC Branding) ──────────────────────────────────────────────────
BG_DARK    = (9, 13, 26)
TEAL       = (0, 200, 154)
EMBER      = (255, 90, 40)
TEXT_WHITE = (236, 241, 255)
TEXT_MUTED = (104, 116, 143)
CARD_BG    = (18, 25, 46)


def get_yt_token() -> str:
    if not YT_RT:
        return ""
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id":     YT_CLIENT_ID,
        "client_secret": YT_CLIENT_SEC,
        "refresh_token": YT_RT,
        "grant_type":    "refresh_token",
    }, timeout=15)
    return r.json().get("access_token", "")


def get_shopify_product() -> dict:
    page = random.randint(1, 8)
    url  = f"https://{SHOPIFY_DOMAIN}/products.json?limit=50&page={page}"
    r    = requests.get(url, timeout=15)
    prods = r.json().get("products", [])
    if not prods:
        r     = requests.get(f"https://{SHOPIFY_DOMAIN}/products.json?limit=50", timeout=15)
        prods = r.json().get("products", [])
    if not prods:
        raise RuntimeError("Keine Shopify Produkte gefunden")
    p = random.choice(prods)
    return {
        "title": p.get("title", "Top Produkt"),
        "price": p.get("variants", [{}])[0].get("price", "29.99"),
        "handle": p.get("handle", ""),
        "img_url": (p.get("images") or [{}])[0].get("src", ""),
    }


def download_image(url: str) -> Image.Image | None:
    if not url:
        return None
    try:
        r = requests.get(url, timeout=15)
        img = Image.open(BytesIO(r.content)).convert("RGB")
        return img
    except Exception:
        return None


def make_frame(prod: dict, product_img: Image.Image | None, frame_idx: int, total_frames: int) -> Image.Image:
    frame = Image.new("RGB", (W, H), BG_DARK)
    draw  = ImageDraw.Draw(frame)

    # Hintergrund-Gradient (einfach via Streifen)
    for y in range(H):
        ratio = y / H
        r2 = int(BG_DARK[0] + (CARD_BG[0] - BG_DARK[0]) * ratio * 0.5)
        g2 = int(BG_DARK[1] + (CARD_BG[1] - BG_DARK[1]) * ratio * 0.5)
        b2 = int(BG_DARK[2] + (CARD_BG[2] - BG_DARK[2]) * ratio * 0.5)
        draw.line([(0, y), (W, y)], fill=(r2, g2, b2))

    # Accent-Linie oben
    draw.rectangle([(0, 0), (W, 8)], fill=TEAL)

    # Produktbild (zentriert, oben)
    img_y_start = 80
    img_area_h  = 900
    if product_img:
        img = product_img.copy()
        img_ratio = img.width / img.height
        if img_ratio > (W - 120) / img_area_h:
            new_w = W - 120
            new_h = int(new_w / img_ratio)
        else:
            new_h = img_area_h
            new_w = int(new_h * img_ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        x_off = (W - new_w) // 2
        y_off = img_y_start + (img_area_h - new_h) // 2
        frame.paste(img, (x_off, y_off))

    # Dunkle Overlay-Box unten
    box_y = 1020
    draw.rectangle([(40, box_y), (W - 40, H - 40)], fill=CARD_BG, outline=(*TEAL, 80), width=2)

    # Fonts (System-Fallback)
    try:
        font_big   = ImageFont.truetype("/System/Library/Fonts/HelveticaNeue.ttc", 64)
        font_mid   = ImageFont.truetype("/System/Library/Fonts/HelveticaNeue.ttc", 48)
        font_small = ImageFont.truetype("/System/Library/Fonts/HelveticaNeue.ttc", 36)
        font_mono  = ImageFont.truetype("/System/Library/Fonts/Courier.ttc", 40)
    except Exception:
        font_big   = ImageFont.load_default()
        font_mid   = font_big
        font_small = font_big
        font_mono  = font_big

    # Titel (mehrzeilig)
    title = prod["title"]
    lines = textwrap.wrap(title, width=22)[:3]
    ty = box_y + 40
    for line in lines:
        draw.text((80, ty), line, font=font_big, fill=TEXT_WHITE)
        ty += 76

    # Preis
    price_text = f"€ {prod['price']}"
    draw.text((80, ty + 20), price_text, font=font_mono, fill=TEAL)

    # Shop-Link
    link = f"ineedit.com.co"
    draw.text((80, H - 140), "👉 " + link, font=font_small, fill=TEXT_MUTED)

    # Hashtags
    tags = "#smarthome #gadgets #deals #shorts #onlineshop"
    draw.text((80, H - 90), tags, font=font_small, fill=(*TEXT_MUTED, 180))

    # Pulse-Dot (animiert)
    progress = frame_idx / max(total_frames - 1, 1)
    dot_x = int(80 + progress * (W - 160))
    draw.ellipse([(dot_x - 6, H - 44), (dot_x + 6, H - 32)], fill=TEAL)
    draw.rectangle([(80, H - 42), (dot_x, H - 34)], fill=(*TEAL, 100))

    return frame


def create_video(prod: dict, out_path: str) -> bool:
    log.info("Erstelle Video: %s", prod["title"][:50])
    product_img = download_image(prod["img_url"])
    total_frames = FPS * DUR

    with tempfile.TemporaryDirectory() as tmp:
        frames_dir = Path(tmp) / "frames"
        frames_dir.mkdir()

        for i in range(total_frames):
            frame = make_frame(prod, product_img, i, total_frames)
            frame.save(frames_dir / f"frame_{i:05d}.png")
            if i % 30 == 0:
                log.info("Frame %d/%d", i, total_frames)

        # ffmpeg: PNG-Sequenz → MP4
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(FPS),
            "-i", str(frames_dir / "frame_%05d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            "-crf", "23",
            out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode != 0:
            log.error("ffmpeg Fehler: %s", result.stderr.decode())
            return False

    log.info("Video erstellt: %s", out_path)
    return True


def upload_to_youtube(video_path: str, prod: dict, token: str) -> str | None:
    title = f"🔥 {prod['title'][:80]} | Deal des Tages"
    desc  = (
        f"{prod['title']}\n\n"
        f"💶 Jetzt für nur €{prod['price']}\n"
        f"👉 {SHOP_URL}/products/{prod['handle']}\n\n"
        f"#Shorts #smarthome #gadgets #deals #onlineshop #ecommerce #shopify"
    )
    metadata = {
        "snippet": {
            "title": title,
            "description": desc,
            "tags": ["Shorts", "deals", "smarthome", "gadgets", "onlineshop", "ecommerce"],
            "categoryId": "26",  # Howto & Style
            "defaultLanguage": "de",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    # Resumable Upload
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "video/mp4",
        "X-Upload-Content-Length": str(Path(video_path).stat().st_size),
    }
    init_url = (
        "https://www.googleapis.com/upload/youtube/v3/videos"
        "?uploadType=resumable&part=snippet,status"
    )
    r = requests.post(init_url, headers=headers, json=metadata, timeout=30)
    if r.status_code != 200:
        log.error("Upload-Init Fehler: %s %s", r.status_code, r.text[:200])
        return None

    upload_url = r.headers.get("Location")
    if not upload_url:
        log.error("Kein Location-Header")
        return None

    log.info("Lade Video hoch: %s", video_path)
    with open(video_path, "rb") as f:
        upload_r = requests.put(
            upload_url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4"},
            data=f,
            timeout=300,
        )

    if upload_r.status_code in (200, 201):
        vid_id = upload_r.json().get("id", "?")
        vid_url = f"https://www.youtube.com/shorts/{vid_id}"
        log.info("✅ YouTube Short hochgeladen: %s", vid_url)
        return vid_url
    else:
        log.error("Upload Fehler: %s %s", upload_r.status_code, upload_r.text[:300])
        return None


def main():
    test_mode = "--test" in sys.argv

    prod = get_shopify_product()
    log.info("Produkt: %s | €%s", prod["title"], prod["price"])

    out_dir = Path(__file__).parent.parent / "data" / "youtube_shorts"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp    = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = str(out_dir / f"short_{stamp}.mp4")

    ok = create_video(prod, out_path)
    if not ok:
        log.error("Video-Erstellung fehlgeschlagen")
        sys.exit(1)

    if test_mode:
        log.info("Test-Modus: Video gespeichert als %s (kein Upload)", out_path)
        return

    token = get_yt_token()
    if not token:
        log.error("Kein YouTube Token — setze YOUTUBE_REFRESH_TOKEN in .env")
        sys.exit(1)

    url = upload_to_youtube(out_path, prod, token)
    if url:
        print(f"✅ {url}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
