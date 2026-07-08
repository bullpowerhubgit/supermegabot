#!/usr/bin/env python3
"""
Einmaliges Twitter/X Login via twikit — Cookies werden gespeichert.
Danach funktioniert post_twitter() vollautomatisch ohne API-Limits.

Ausführen: python3 setup_twitter_cookies.py
"""
import asyncio, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
with open(".env") as f:
    for line in f:
        l = line.strip()
        if l and not l.startswith("#") and "=" in l:
            k, v = l.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

COOKIES_PATH = Path("data/twitter_cookies.json")

async def main():
    from twikit import Client

    username = os.getenv("TWITTER_USERNAME", "rudibot84")
    email    = os.getenv("TWITTER_EMAIL", "")
    password = os.getenv("TWITTER_PASSWORD", "")

    if not password:
        print("TWITTER_PASSWORD fehlt in .env!")
        print("Bitte in .env eintragen: TWITTER_PASSWORD=DeinPasswort")
        return

    print(f"Login als @{username}...")
    client = Client("en-US")

    try:
        await client.login(
            auth_info_1=username,
            auth_info_2=email or username,
            password=password,
        )
        client.save_cookies(str(COOKIES_PATH))
        print(f"✅ Login erfolgreich! Cookies gespeichert: {COOKIES_PATH}")

        tweet = await client.create_tweet(text="SuperMegaBot Autopost Test ✅ — ineedit.com.co")
        print(f"✅ Test-Tweet gepostet! ID: {tweet.id}")
    except Exception as e:
        print(f"❌ Login fehlgeschlagen: {e}")

if __name__ == "__main__":
    asyncio.run(main())
