"""
PostingCoordinator — Globaler Posting-Lock der Doppelposts verhindert.

ALLE Posting-Systeme (BrutalAdsEngine, SOCIAL POST, TIKTOK BLAST, etc.)
müssen diesen Lock prüfen bevor sie posten. Nur eines kann gleichzeitig aktiv sein.

Qualitätsprüfung: Jeder Post läuft durch PostGuard bevor er veröffentlicht wird.
"""
import asyncio
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_DB_PATH = Path(os.getenv("DATA_DIR", "data")) / "posting_coordinator.db"

# Plattform-Limits pro Tag (konsistent mit organic_traffic_manager.py)
PLATFORM_DAILY_LIMITS = {
    "instagram": 2,
    "facebook": 2,
    "tiktok": 2,
    "pinterest": 3,
    "twitter": 3,
    "x": 3,
    "reddit": 1,
    "linkedin": 1,
    "telegram": 50,
    "discord": 5,
    "youtube": 1,
}

MIN_GAP_SECONDS = {
    "instagram": 4 * 3600,
    "facebook": 8 * 3600,   # FB spamblockt bei <6h — 8h Sicherheitspuffer
    "reddit": 12 * 3600,
    "linkedin": 10 * 3600,
    "tiktok": 4 * 3600,
    "twitter": 2 * 3600,
    "x": 2 * 3600,
    "default": 1800,  # 30 min
}


@dataclass
class PostingSession:
    system: str           # "brutal_ads", "social_post", "organic_traffic", etc.
    platform: str
    started_at: float
    content_preview: str


class PostingCoordinator:
    """Verhindert Doppelposts über alle Systeme."""

    def __init__(self):
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS posting_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    system TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    content_preview TEXT,
                    content_hash TEXT,
                    posted_at REAL NOT NULL,
                    status TEXT DEFAULT 'ok',
                    guard_score INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS posting_lock (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    system TEXT,
                    platform TEXT,
                    locked_at REAL,
                    expires_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_posted_at ON posting_log(posted_at);
                CREATE INDEX IF NOT EXISTS idx_platform_posted ON posting_log(platform, posted_at);
            """)

    def is_locked(self) -> tuple[bool, Optional[str]]:
        """Gibt zurück ob gerade ein anderes System postet."""
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM posting_lock WHERE id=1").fetchone()
            if not row:
                return False, None
            if row["expires_at"] < time.time():
                conn.execute("DELETE FROM posting_lock WHERE id=1")
                return False, None
            return True, row["system"]

    def acquire_lock(self, system: str, platform: str, timeout: int = 60) -> bool:
        """Versuche den globalen Posting-Lock zu erwerben."""
        locked, who = self.is_locked()
        if locked and who != system:
            log.warning("Posting-Lock belegt von '%s' — '%s' muss warten", who, system)
            return False
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO posting_lock (id, system, platform, locked_at, expires_at)
                VALUES (1, ?, ?, ?, ?)
            """, (system, platform, time.time(), time.time() + timeout))
        return True

    def release_lock(self):
        """Posting-Lock freigeben."""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM posting_lock WHERE id=1")

    def can_post(self, platform: str, system: str = "any") -> tuple[bool, str]:
        """Prüft ob auf dieser Plattform heute noch gepostet werden darf."""
        platform_key = platform.lower().strip()
        daily_limit = PLATFORM_DAILY_LIMITS.get(platform_key, 2)
        min_gap = MIN_GAP_SECONDS.get(platform_key, MIN_GAP_SECONDS["default"])

        now = time.time()
        day_start = now - (now % 86400)  # Beginn des aktuellen Tages (UTC)

        with self._get_conn() as conn:
            # Tages-Limit prüfen
            today_count = conn.execute("""
                SELECT COUNT(*) as cnt FROM posting_log
                WHERE platform=? AND posted_at > ? AND status='ok'
            """, (platform_key, day_start)).fetchone()["cnt"]

            if today_count >= daily_limit:
                return False, f"Tages-Limit erreicht ({today_count}/{daily_limit})"

            # Mindest-Abstand prüfen
            last_post = conn.execute("""
                SELECT posted_at FROM posting_log
                WHERE platform=? AND status='ok'
                ORDER BY posted_at DESC LIMIT 1
            """, (platform_key,)).fetchone()

            if last_post and (now - last_post["posted_at"]) < min_gap:
                wait = int(min_gap - (now - last_post["posted_at"])) // 60
                return False, f"Mindestabstand: noch {wait} Min warten"

        return True, "ok"

    def log_post(self, system: str, platform: str, content: str,
                 guard_score: int = 0, status: str = "ok"):
        """Logge einen veröffentlichten Post."""
        import hashlib
        content_hash = hashlib.md5(content.encode()).hexdigest()[:16]
        preview = content[:100].replace("\n", " ")

        with self._get_conn() as conn:
            # Duplikat-Check (gleicher Hash = Doppelpost)
            dup = conn.execute(
                "SELECT id FROM posting_log WHERE content_hash=? AND posted_at > ?",
                (content_hash, time.time() - 86400)
            ).fetchone()
            if dup:
                log.warning("PostingCoordinator: Duplikat-Post blockiert (%s)", preview[:50])
                return False

            conn.execute("""
                INSERT INTO posting_log (system, platform, content_preview, content_hash, posted_at, status, guard_score)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (system, platform, preview, content_hash, time.time(), status, guard_score))
        return True

    def get_today_stats(self) -> dict:
        """Heutige Posting-Statistiken."""
        now = time.time()
        day_start = now - (now % 86400)
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT platform, system, COUNT(*) as cnt
                FROM posting_log
                WHERE posted_at > ? AND status='ok'
                GROUP BY platform, system
                ORDER BY cnt DESC
            """, (day_start,)).fetchall()

        stats: dict = {}
        for row in rows:
            p = row["platform"]
            limit = PLATFORM_DAILY_LIMITS.get(p, 2)
            if p not in stats:
                stats[p] = {"today": 0, "limit": limit, "remaining": limit, "systems": []}
            stats[p]["today"] += row["cnt"]
            stats[p]["remaining"] = max(0, limit - stats[p]["today"])
            stats[p]["systems"].append(row["system"])
        return stats

    def get_active_lock(self) -> Optional[dict]:
        """Aktuell aktiver Posting-Lock."""
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM posting_lock WHERE id=1").fetchone()
            if row and row["expires_at"] > time.time():
                return dict(row)
        return None

    @asynccontextmanager
    async def posting_session(self, system: str, platform: str, timeout: int = 120):
        """Context-Manager für Posting-Sessions — automatisches Lock/Release."""
        acquired = self.acquire_lock(system, platform, timeout)
        if not acquired:
            locked, who = self.is_locked()
            raise RuntimeError(f"Posting-Konflikt: {system} wartet auf {who}")
        try:
            yield self
        finally:
            self.release_lock()

    async def safe_post(self, system: str, platform: str, content: str,
                        post_fn, guard_check: bool = True) -> dict:
        """
        Sicherer Post-Wrapper:
        1. Prüft ob auf Plattform heute noch gepostet werden darf
        2. Erwirbt Posting-Lock
        3. Läuft PostGuard durch (URL-Check, Spam, Duplikat, Qualität)
        4. Postet wenn alles OK
        5. Loggt den Post
        6. Gibt Lock frei
        """
        # 1. Tages-Limit prüfen
        can, reason = self.can_post(platform, system)
        if not can:
            log.info("[%s] %s: Nicht gepostet — %s", system, platform, reason)
            return {"ok": False, "reason": reason}

        # 2. Duplikat-Content-Check (vor Lock)
        import hashlib
        content_hash = hashlib.md5(content.encode()).hexdigest()[:16]
        with self._get_conn() as conn:
            dup = conn.execute(
                "SELECT id FROM posting_log WHERE content_hash=? AND posted_at > ?",
                (content_hash, time.time() - 86400)
            ).fetchone()
        if dup:
            return {"ok": False, "reason": "Duplikat-Content (bereits heute gepostet)"}

        # 3. PostGuard — Inhaltsprüfung + Auto-Reparatur
        guard_score = 0
        if guard_check:
            try:
                from modules.post_guardian import check_post, auto_repair_post
                guard_result = await check_post(platform, content)
                if not guard_result.get("ok", True):
                    rep = await auto_repair_post(content, platform)
                    if rep.get("ok"):
                        content = rep["repaired_text"]
                        log.info("[%s] PostGuardian Auto-Reparatur: %s", system, rep.get("changes", []))
                        guard_result = await check_post(platform, content)
                    if not guard_result.get("ok", True):
                        reason = "; ".join(guard_result.get("errors", ["unbekannt"])[:2])
                        log.warning("[%s] PostGuardian BLOCKIERT [%s]: %s", system, platform, reason)
                        return {"ok": False, "reason": f"PostGuard: {reason}"}
            except Exception as e:
                log.warning("PostGuardian nicht verfügbar: %s", e)

        # 4. Lock erwerben
        if not self.acquire_lock(system, platform):
            return {"ok": False, "reason": f"Posting-Konflikt mit anderem System"}

        try:
            # 5. Posten
            result = await post_fn(content)
            status = "ok" if result else "failed"
            self.log_post(system, platform, content, guard_score, status)
            log.info("[%s] ✅ %s gepostet (score=%d)", system, platform, guard_score)
            return {"ok": bool(result), "platform": platform, "guard_score": guard_score}
        except Exception as e:
            self.log_post(system, platform, content, guard_score, "error")
            log.error("[%s] Post-Fehler auf %s: %s", system, platform, e)
            return {"ok": False, "reason": str(e)}
        finally:
            self.release_lock()


# Singleton
_coordinator = PostingCoordinator()


def get_coordinator() -> PostingCoordinator:
    return _coordinator


def can_post_now(platform: str, system: str = "any") -> tuple[bool, str]:
    return _coordinator.can_post(platform, system)


def get_posting_status() -> dict:
    locked, who = _coordinator.is_locked()
    return {
        "locked": locked,
        "active_system": who,
        "today_stats": _coordinator.get_today_stats(),
        "active_lock": _coordinator.get_active_lock(),
    }
