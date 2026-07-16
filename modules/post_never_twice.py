#!/usr/bin/env python3
"""
Post Never-Twice Engine — DAUERHAFT
===================================
Ein Fehler darf NIE zweimal passieren.

1. Jeder Block/Fail wird mit Fingerprint + Content-Hash gespeichert
2. Gleicher Content → sofort BLOCK (lifetime)
3. Gleiche Fehlerklasse 2× → permanent rule (Regex/Keyword) wird gelernt
4. Alle Guards rufen check_never_twice() VOR dem Senden auf
5. remember_block() NACH jedem Block — fail-closed

DB: data/post_never_twice.db (survives restarts)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Iterable, List, Tuple

log = logging.getLogger("PostNeverTwice")

_ROOT = Path(__file__).resolve().parent.parent
_DB = Path(os.getenv("DATA_DIR", str(_ROOT / "data"))) / "post_never_twice.db"

# ── Seed permanent rules (hardcoded forever) ─────────────────────────────────
_SEED_RULES: list[tuple[str, str, str]] = [
    ("myshopify", r"myshopify\.com", "Store-URL must be ineedit.com.co"),
    ("none_placeholder", r"(?i)Hallo\s+None|—\s*None\b|für\s+None\b|NoneType|:\s*None\b", "Python None in post"),
    ("placeholder", r"(?i)\[PLACEHOLDER\]|\[TODO\]|\[PRODUKT\]|\[LINK\]|TODO:|FIXME:", "Placeholder text"),
    ("ai_disclosure", r"(?i)als\s+ki[- ]sprachmodell|as\s+an\s+ai\s+model|ich\s+bin\s+(eine\s+)?ki\b", "AI disclosure"),
    ("offtopic_hn", r"(?i)show\s*hn:?|ask\s*hn:?|hacker\.?news", "Hacker News off-topic"),
    # KEIN bare \bwar\b — deutsches Präteritum "war" (z.B. "war früher")
    ("offtopic_news", r"(?i)\b(polizei|vancouver\s+pd|wahlen?\b|krieg|ukraine\s+krieg|warfare|warzone|world\s+war)\b", "News/politics off-topic"),
    ("fake_product", r"(?i)\bblender\b|3d\s*modellierung|quick escape button", "Fake product / HN scrape"),
    ("traceback", r"(?i)Traceback\s*\(most recent|File\s+\".*\",\s+line\s+\d+", "Python traceback in post"),
    ("localhost", r"localhost|127\.0\.0\.1|yourstore|example\.com", "Dev/placeholder domain"),
    ("old_ds24", r"checkout-ds24\.com/product/668035", "Deprecated DS24 product id"),
    # API-URL als "Content" = Extraktion kaputt — immer blocken, nie posten
    ("api_url_as_content", r"(?i)^https?://api\.(linkedin|twitter|facebook|x)\.com/\S*$", "API-URL als Post-Inhalt (Extraktion fehlgeschlagen)"),
]

# Map free-text reasons → rule ids for auto-promotion
_REASON_TO_RULE: list[tuple[str, str]] = [
    (r"myshopify|ineedit\.com\.co", "myshopify"),
    (r"None-Placeholder|Hallo None|— None", "none_placeholder"),
    (r"Placeholder|PLACEHOLDER|TODO", "placeholder"),
    (r"KI-Offenbarung|AI disclosure|Sprachmodell", "ai_disclosure"),
    (r"Show HN|Hacker News|Off-Topic", "offtopic_hn"),
    (r"Polizei|Politik|Vancouver|Off-Topic", "offtopic_news"),
    (r"Blender|3D Modell|Fake", "fake_product"),
    (r"Traceback|Stack-Trace|Code-Fehler", "traceback"),
    (r"localhost|example\.com", "localhost"),
    (r"Duplikat|duplicate", "duplicate"),
    (r"real_url|NoneType|ClientResponseError", "http_guard_crash"),
]


def _conn() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB), timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,          -- block|fail|sent
                platform TEXT,
                content_hash TEXT,
                fingerprint TEXT,
                reason TEXT,
                preview TEXT,
                source_module TEXT,
                ts REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS content_blacklist (
                content_hash TEXT PRIMARY KEY,
                platform TEXT,
                reason TEXT,
                first_seen REAL,
                hits INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS error_classes (
                fingerprint TEXT PRIMARY KEY,
                reason_sample TEXT,
                hits INTEGER DEFAULT 1,
                first_seen REAL,
                last_seen REAL,
                promoted INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS permanent_rules (
                rule_id TEXT PRIMARY KEY,
                pattern TEXT NOT NULL,
                description TEXT,
                hits INTEGER DEFAULT 0,
                created_at REAL,
                source TEXT DEFAULT 'seed'
            );
            CREATE INDEX IF NOT EXISTS idx_events_hash ON events(content_hash);
            CREATE INDEX IF NOT EXISTS idx_events_fp ON events(fingerprint);
            """
        )
        now = time.time()
        for rid, pat, desc in _SEED_RULES:
            # UPSERT: Seed-Patterns immer aktualisieren (Bugfixes wie \bwar\b → warfare)
            c.execute(
                """INSERT INTO permanent_rules(rule_id,pattern,description,hits,created_at,source)
                   VALUES(?,?,?,0,?,?)
                   ON CONFLICT(rule_id) DO UPDATE SET
                     pattern=excluded.pattern,
                     description=excluded.description,
                     source='seed'""",
                (rid, pat, desc, now, "seed"),
            )
        # Toxische Blacklist-Einträge: reine API-URLs (Extraktions-Bug) entfernen
        try:
            c.execute(
                "DELETE FROM content_blacklist WHERE reason LIKE '%api.linkedin.com%' "
                "OR reason LIKE '%ugcPosts%' OR reason LIKE '%text_extraktion%'"
            )
        except Exception:
            pass
        try:
            for bad_url in (
                "https://api.linkedin.com/v2/ugcPosts",
                "https://api.linkedin.com/v2/shares",
                "https://api.linkedin.com/v2/posts",
            ):
                for plat in ("linkedin", "default", "unknown", ""):
                    ch = _content_hash(bad_url, plat)
                    c.execute("DELETE FROM content_blacklist WHERE content_hash=?", (ch,))
        except Exception:
            pass


def _content_hash(text: str, platform: str = "") -> str:
    norm = re.sub(r"\s+", " ", (text or "").strip().lower())
    return hashlib.sha256(f"{platform}|{norm}".encode()).hexdigest()[:32]


def _fingerprint(platform: str, reasons: Iterable[str]) -> str:
    joined = "|".join(sorted({re.sub(r"\s+", " ", r.strip().lower())[:80] for r in reasons if r}))
    # collapse to error class keywords
    classes = []
    for r in reasons:
        for pat, rid in _REASON_TO_RULE:
            if re.search(pat, r, re.I):
                classes.append(rid)
                break
        else:
            classes.append(hashlib.md5(r.encode()).hexdigest()[:8])
    key = f"{platform.lower()}:" + ",".join(sorted(set(classes)))
    return hashlib.sha256(key.encode()).hexdigest()[:24]


def _load_rules() -> list[tuple[str, re.Pattern, str]]:
    init_db()
    out = []
    with _conn() as c:
        rows = c.execute("SELECT rule_id, pattern, description FROM permanent_rules").fetchall()
    for r in rows:
        try:
            out.append((r["rule_id"], re.compile(r["pattern"], re.I | re.DOTALL), r["description"] or ""))
        except re.error as e:
            log.warning("Invalid permanent rule %s: %s", r["rule_id"], e)
    return out


def check_never_twice(text: str, platform: str = "default") -> Tuple[bool, List[str]]:
    """
    Returns (ok, errors). ok=False → MUST NOT post.
    Checks: content blacklist + permanent learned/seed rules.
    """
    init_db()
    errors: List[str] = []
    platform = (platform or "default").lower()
    text = text or ""
    ch = _content_hash(text, platform)

    # 1) Exact content blacklisted forever
    with _conn() as c:
        row = c.execute(
            "SELECT reason, hits FROM content_blacklist WHERE content_hash=?", (ch,)
        ).fetchone()
        if row:
            c.execute(
                "UPDATE content_blacklist SET hits=hits+1 WHERE content_hash=?", (ch,)
            )
            errors.append(f"NEVER-TWICE: exakter Content bereits blockiert ({row['reason'][:80]})")

    # 2) Permanent rules (seed + learned)
    for rid, cre, desc in _load_rules():
        if cre.search(text):
            errors.append(f"NEVER-TWICE rule[{rid}]: {desc}")
            with _conn() as c:
                c.execute(
                    "UPDATE permanent_rules SET hits=hits+1 WHERE rule_id=?", (rid,)
                )

    if errors:
        log.warning("NeverTwice BLOCK [%s]: %s", platform, errors)
        return False, errors
    return True, []


def _sanitize_reason(r: str) -> str:
    """Strip recursive NEVER-TWICE: prefixes before storing. Max 120 chars."""
    r = str(r).strip()
    # peel off nested "NEVER-TWICE: exakter Content bereits blockiert (…)" layers
    for _ in range(5):
        if not r.startswith("NEVER-TWICE:"):
            break
        m = re.search(r'\((.+)\)\s*$', r, re.DOTALL)
        if m:
            r = m.group(1).strip()
        else:
            r = r[len("NEVER-TWICE:"):].strip()
    return r[:120]


def remember_block(
    text: str,
    platform: str,
    reasons: List[str],
    source_module: str = "unknown",
    kind: str = "block",
) -> dict:
    """
    Persist a block/fail so it can never succeed again.
    After 2 hits of same fingerprint → promote permanent rule if mappable.
    """
    init_db()
    platform = (platform or "default").lower()
    reasons = [_sanitize_reason(r) for r in (reasons or ["unknown"]) if r]
    ch = _content_hash(text, platform)
    fp = _fingerprint(platform, reasons)
    now = time.time()
    preview = (text or "")[:160].replace("\n", " ")
    reason_s = " | ".join(reasons)[:500]

    with _conn() as c:
        c.execute(
            """INSERT INTO events(kind,platform,content_hash,fingerprint,reason,preview,source_module,ts)
               VALUES(?,?,?,?,?,?,?,?)""",
            (kind, platform, ch, fp, reason_s, preview, source_module, now),
        )
        # content blacklist
        existing = c.execute(
            "SELECT hits FROM content_blacklist WHERE content_hash=?", (ch,)
        ).fetchone()
        if existing:
            c.execute(
                "UPDATE content_blacklist SET hits=hits+1, reason=? WHERE content_hash=?",
                (reason_s, ch),
            )
        else:
            c.execute(
                """INSERT INTO content_blacklist(content_hash,platform,reason,first_seen,hits)
                   VALUES(?,?,?,?,1)""",
                (ch, platform, reason_s, now),
            )
        # error class counter
        row = c.execute(
            "SELECT hits, promoted FROM error_classes WHERE fingerprint=?", (fp,)
        ).fetchone()
        if row:
            hits = row["hits"] + 1
            c.execute(
                "UPDATE error_classes SET hits=?, last_seen=?, reason_sample=? WHERE fingerprint=?",
                (hits, now, reason_s, fp),
            )
            promoted = row["promoted"]
        else:
            hits = 1
            promoted = 0
            c.execute(
                """INSERT INTO error_classes(fingerprint,reason_sample,hits,first_seen,last_seen,promoted)
                   VALUES(?,?,1,?,?,0)""",
                (fp, reason_s, now, now),
            )

        # Auto-promote after 2 identical error-class hits
        newly_promoted = []
        if hits >= 2 and not promoted:
            for r in reasons:
                for pat, rid in _REASON_TO_RULE:
                    if re.search(pat, r, re.I):
                        # ensure rule exists / mark promoted
                        seed = next((s for s in _SEED_RULES if s[0] == rid), None)
                        if seed:
                            c.execute(
                                """INSERT OR IGNORE INTO permanent_rules(rule_id,pattern,description,hits,created_at,source)
                                   VALUES(?,?,?,1,?,?)""",
                                (seed[0], seed[1], seed[2], now, "auto_promote"),
                            )
                            c.execute(
                                "UPDATE permanent_rules SET hits=hits+1 WHERE rule_id=?", (rid,)
                            )
                            newly_promoted.append(rid)
                        break
            c.execute("UPDATE error_classes SET promoted=1 WHERE fingerprint=?", (fp,))

    log.info(
        "NeverTwice remembered [%s] hits=%s fp=%s promoted=%s",
        platform, hits, fp, newly_promoted if hits >= 2 else [],
    )
    return {
        "content_hash": ch,
        "fingerprint": fp,
        "hits": hits,
        "promoted": newly_promoted,
    }


def remember_sent(text: str, platform: str, source_module: str = "unknown") -> None:
    init_db()
    ch = _content_hash(text, platform)
    with _conn() as c:
        c.execute(
            """INSERT INTO events(kind,platform,content_hash,fingerprint,reason,preview,source_module,ts)
               VALUES(?,?,?,?,?,?,?,?)""",
            ("sent", platform.lower(), ch, "", "ok", (text or "")[:160], source_module, time.time()),
        )


def import_legacy_blocks() -> dict:
    """Import blocked rows from post_gateway / post_guardian DBs."""
    init_db()
    imported = 0
    for db_name, table, cols in (
        ("post_gateway.db", "blocked", ("platform", "reason", "preview")),
        ("post_guardian.db", "blocked", None),  # flexible
    ):
        path = _ROOT / "data" / db_name
        if not path.exists():
            continue
        try:
            with sqlite3.connect(str(path)) as src:
                src.row_factory = sqlite3.Row
                try:
                    rows = src.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT 500").fetchall()
                except sqlite3.Error:
                    continue
                for row in rows:
                    keys = row.keys()
                    platform = row["platform"] if "platform" in keys else "unknown"
                    reason = row["reason"] if "reason" in keys else "legacy"
                    # content may be in various columns
                    text = ""
                    for k in ("preview", "content", "text", "body"):
                        if k in keys and row[k]:
                            text = str(row[k])
                            break
                    if not text and len(row) > 1:
                        text = str(row[1]) if row[1] else ""
                    if text:
                        remember_block(text, str(platform), [str(reason)], source_module=f"import:{db_name}")
                        imported += 1
        except Exception as e:
            log.warning("legacy import %s: %s", db_name, e)
    return {"imported": imported}


def stats() -> dict:
    init_db()
    with _conn() as c:
        return {
            "events": c.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            "blacklisted_contents": c.execute("SELECT COUNT(*) FROM content_blacklist").fetchone()[0],
            "error_classes": c.execute("SELECT COUNT(*) FROM error_classes").fetchone()[0],
            "permanent_rules": c.execute("SELECT COUNT(*) FROM permanent_rules").fetchone()[0],
            "promoted_classes": c.execute(
                "SELECT COUNT(*) FROM error_classes WHERE promoted=1"
            ).fetchone()[0],
            "top_rules": [
                dict(r)
                for r in c.execute(
                    "SELECT rule_id, hits, description FROM permanent_rules ORDER BY hits DESC LIMIT 10"
                ).fetchall()
            ],
        }


def self_check() -> dict:
    """Offline regression: same bad content blocked twice; second time via memory."""
    init_db()
    sample = "FAKE NEVER-TWICE TEST [PLACEHOLDER] myshopify.com Hallo None Blender"
    platform = "twitter"
    # clear this hash only for test? use unique sample with timestamp
    sample = f"{sample} {int(time.time())}"
    ok1, e1 = check_never_twice(sample, platform)
    # first time may pass never-twice content blacklist but rules should catch
    # force remember
    remember_block(sample, platform, e1 or ["placeholder test"], source_module="self_check")
    ok2, e2 = check_never_twice(sample, platform)
    # same content must fail second time
    second_blocked = not ok2
    # seed rules must catch myshopify without memory
    ok3, e3 = check_never_twice("Buy now https://x.myshopify.com/products/1 Shopify deal", "facebook")
    rules_ok = not ok3
    return {
        "ok": second_blocked and rules_ok,
        "second_blocked": second_blocked,
        "rules_block_myshopify": rules_ok,
        "e2": e2,
        "e3": e3,
        "stats": stats(),
    }


if __name__ == "__main__":
    import_legacy_blocks()
    print(json.dumps(self_check(), indent=2, ensure_ascii=False))
