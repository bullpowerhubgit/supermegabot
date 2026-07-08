#!/usr/bin/env python3
"""
Auto-Refresh der Twitter/X Session-Cookies aus Chrome.
Läuft täglich via Scheduler — hält Twitter-Auth immer aktuell.
"""
import sqlite3, shutil, os, json, tempfile, subprocess, logging
from pathlib import Path
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2

log = logging.getLogger("TwitterCookieRefresher")
COOKIES_PATH = Path(__file__).parent.parent / "data" / "twitter_cookies.json"

def _chrome_aes_key():
    result = subprocess.run(
        ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage", "-a", "Chrome"],
        capture_output=True, text=True
    )
    raw = result.stdout.strip()
    if not raw:
        return None
    return PBKDF2(raw.encode(), b"saltysalt", 16, 1003)

def _decrypt(enc_bytes, aes_key):
    enc = bytes(enc_bytes)
    if enc[:3] != b"v10":
        return enc.decode("utf-8", errors="ignore")
    iv = b" " * 16
    cipher = AES.new(aes_key, AES.MODE_CBC, IV=iv)
    dec = cipher.decrypt(enc[3:])
    pad = dec[-1]
    raw = dec[:-pad]
    if len(raw) > 32:
        raw = raw[32:]
    return raw.decode("utf-8", errors="ignore").strip()

def refresh_cookies() -> bool:
    """Extract Twitter cookies from Chrome and save for API use."""
    aes_key = _chrome_aes_key()
    if not aes_key:
        log.warning("Chrome AES key not available")
        return False

    chrome_path = os.path.expanduser(
        "~/Library/Application Support/Google/Chrome/Default/Cookies"
    )
    if not os.path.exists(chrome_path):
        log.warning("Chrome Cookies DB not found")
        return False

    tmp = tempfile.mktemp(suffix=".db")
    shutil.copy2(chrome_path, tmp)
    try:
        conn = sqlite3.connect(tmp)
        cur = conn.cursor()
        cur.execute("""
            SELECT name, value, encrypted_value, host_key
            FROM cookies
            WHERE name IN ('auth_token','ct0','twid','guest_id','_twpid')
            AND (host_key LIKE '%.x.com' OR host_key LIKE '%.twitter.com')
        """)
        rows = cur.fetchall()
        conn.close()
    finally:
        os.unlink(tmp)

    result = {}
    for name, val, enc, host in rows:
        v = val if val else _decrypt(enc, aes_key)
        if v and name not in result:
            result[name] = v

    if not result.get("auth_token"):
        log.warning("auth_token not found — is @rudibot84 logged in to Chrome?")
        return False

    COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(COOKIES_PATH, "w") as f:
        json.dump(result, f)
    log.info("Twitter cookies refreshed (%d keys)", len(result))
    return True

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    ok = refresh_cookies()
    if ok:
        with open(COOKIES_PATH) as f:
            d = json.load(f)
        print(f"✅ {len(d)} Cookies gespeichert")
        print(f"  auth_token: {d.get('auth_token','?')[:20]}...")
        print(f"  ct0: {d.get('ct0','?')[:20]}...")
    else:
        print("❌ Cookie-Refresh fehlgeschlagen")
        sys.exit(1)
