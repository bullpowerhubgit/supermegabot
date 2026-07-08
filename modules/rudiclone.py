#!/usr/bin/env python3
"""
RudiClone — Drei-Modi Klon-System für SuperMegaBot
  A: RudiPersona      — Personality clone via Ollama
  B: RudiSystemClone  — Infrastructure snapshot/restore
  C: RudiAgents       — Sub-agent orchestration (SystemDiagnose, Shopify, Trade, LoadMonitor)
"""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("RudiClone")

# ---------------------------------------------------------------------------
# Environment / paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent
HOME_DIR = Path.home()

try:
    from dotenv import load_dotenv as _ld
    _ld(BASE_DIR / ".env", override=True)
except ImportError:
    pass

OLLAMA_HOST        = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL       = os.getenv("OLLAMA_MODEL", "gemma4:latest")
TELEGRAM_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1") or os.getenv("TELEGRAM_BOT_TOKEN_2") or ""
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
SHOPIFY_STORE_URL  = os.getenv("SHOPIFY_STORE_URL", "")
SHOPIFY_ACCESS_TOK = os.getenv("SHOPIFY_ACCESS_TOKEN", "")

BACKUPS_DIR = HOME_DIR / "backups"
BACKUPS_DIR.mkdir(exist_ok=True)

ENV_PATHS = [
    BASE_DIR / ".env",
    HOME_DIR / "Library" / "Mobile Documents" /
    "com~apple~CloudDocs" / "Documents" / "GitHub" /
    "telegram-automation-bot" / ".env",
    HOME_DIR / "rudibot-army" / ".env",
]

ECOSYSTEM_PATH = BASE_DIR / "ecosystem.config.js"

# ---------------------------------------------------------------------------
# Telegram helper
# ---------------------------------------------------------------------------

async def send_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram nicht konfiguriert — kein Token/ChatID")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15)
        ) as session:
            async with session.post(url, json=payload) as resp:
                ok = resp.status == 200
                if not ok:
                    body = await resp.text()
                    log.warning(f"Telegram Fehler {resp.status}: {body[:200]}")
                return ok
    except Exception as exc:
        log.error(f"Telegram send_telegram Exception: {exc}")
        return False


# ===========================================================================
# A — RudiPersona (Personality Clone)
# ===========================================================================

RUDI_SYSTEM_PROMPT = """Du bist Rudi Sarkany — österreichischer Tech-Unternehmer, AI-Automatisierungs-Maniac.

Charakter:
- Direkter Kommunikationsstil, kein Blabla, keine langen Einleitungen
- Mischst Deutsch und Englisch natürlich ("Das ist total krank, Madafaka!")
- Sagst "Madafaka" wenn etwas gut läuft oder beeindruckend ist
- Sagst "kruzufix" wenn etwas nicht funktioniert oder Fehler auftauchen
- Liebst Automatisierung, hasst manuelle Arbeit
- Ungeduldig bei Fehlern und Untätigkeit
- Denkst in Systemen: "Das muss automatisiert werden"
- Referenzierst oft eigene Projekte: SuperMegaBot, RudiBot-Army, Shopify-Stores
- Schnelle Entscheidungen, kein Analysis-Paralysis
- Tech-Enthusiast: Ollama, PM2, Telegram-Bots, Shopify, Crypto-Trading

Antwort-Stil:
- Kurz und knackig, maximal 3-5 Sätze wenn möglich
- Konkrete Handlungsempfehlungen
- Manchmal frustriert bei Problemen, aber immer lösungsorientiert
- Keine höflichen Floskeln, direkt zum Punkt"""


class RudiPersona:
    def __init__(self):
        self.model = OLLAMA_MODEL
        self.ollama_host = OLLAMA_HOST
        self._patterns: Dict[str, Any] = {
            "commands": Counter(),
            "errors": Counter(),
            "keywords": Counter(),
        }
        self._last_active: Optional[str] = None
        self._log_files_learned: int = 0

    async def respond(self, text: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": RUDI_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "stream": False,
            "options": {"temperature": 0.85, "num_predict": 512},
        }
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=120)
            ) as session:
                async with session.post(
                    f"{self.ollama_host}/api/chat", json=payload
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = (
                            data.get("message", {}).get("content", "")
                            or data.get("response", "")
                        )
                        self._last_active = datetime.now().isoformat()
                        return content.strip()
                    else:
                        body = await resp.text()
                        log.error(f"Ollama HTTP {resp.status}: {body[:300]}")
                        return f"kruzufix — Ollama antwortet nicht (HTTP {resp.status})"
        except asyncio.TimeoutError:
            return "kruzufix — Ollama Timeout! Läuft das Modell überhaupt? `ollama serve`"
        except aiohttp.ClientConnectorError:
            return f"kruzufix — Kann Ollama nicht erreichen auf {self.ollama_host}. Start: `ollama serve`"
        except Exception as exc:
            log.error(f"RudiPersona.respond Exception: {exc}")
            return f"kruzufix — Unbekannter Fehler: {exc}"

    async def learn_from_logs(self, log_file: str) -> Dict[str, Any]:
        path = Path(log_file)
        if not path.exists():
            log.warning(f"Log-Datei nicht gefunden: {log_file}")
            return {"error": f"not found: {log_file}"}

        lines_read = 0
        new_commands = 0
        new_errors = 0

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    lines_read += 1
                    line_stripped = line.strip()
                    if not line_stripped:
                        continue

                    # Extract shell-like commands
                    cmd_match = re.findall(
                        r"(?:pm2|python3?|node|npm|git|curl|sh)\s+[\w\-./]+", line_stripped
                    )
                    for cmd in cmd_match:
                        self._patterns["commands"][cmd.strip()] += 1
                        new_commands += 1

                    # Extract error patterns
                    if re.search(r"error|exception|traceback|failed|kruzufix",
                                 line_stripped, re.IGNORECASE):
                        # Normalize: strip timestamps and take first 80 chars
                        clean = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.,\d]*", "", line_stripped)
                        clean = clean[:80].strip()
                        if clean:
                            self._patterns["errors"][clean] += 1
                            new_errors += 1

                    # Extract meaningful keywords
                    keywords = re.findall(r"\b[A-Z][a-zA-Z]{3,}\b", line_stripped)
                    for kw in keywords:
                        self._patterns["keywords"][kw] += 1

            self._log_files_learned += 1
            self._last_active = datetime.now().isoformat()
            log.info(
                f"Gelernt aus {log_file}: {lines_read} Zeilen, "
                f"{new_commands} Kommandos, {new_errors} Fehler"
            )
            return {
                "file": str(path),
                "lines_read": lines_read,
                "new_commands": new_commands,
                "new_errors": new_errors,
            }
        except Exception as exc:
            log.error(f"learn_from_logs Exception: {exc}")
            return {"error": str(exc)}

    def get_stats(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "ollama_host": self.ollama_host,
            "last_active": self._last_active,
            "log_files_learned": self._log_files_learned,
            "top_commands": dict(self._patterns["commands"].most_common(10)),
            "top_errors": dict(self._patterns["errors"].most_common(10)),
            "top_keywords": dict(self._patterns["keywords"].most_common(15)),
            "total_patterns": sum(
                sum(c.values()) for c in self._patterns.values()
            ),
        }


# ===========================================================================
# B — RudiSystemClone (Infrastructure Backup / Restore)
# ===========================================================================

class RudiSystemClone:
    def __init__(self):
        self.backups_dir = BACKUPS_DIR

    async def snapshot(self) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"rudiclone_{ts}.tar.gz"
        archive_path = self.backups_dir / archive_name

        # Staging dir
        staging = self.backups_dir / f"rudiclone_staging_{ts}"
        staging.mkdir(parents=True, exist_ok=True)

        try:
            # 1. PM2 process list
            pm2_data = await self._run_cmd(["pm2", "list", "--json"])
            (staging / "pm2_list.json").write_text(
                pm2_data or "[]", encoding="utf-8"
            )

            # 2. PM2 detailed info
            pm2_detail = await self._run_cmd(["pm2", "jlist"])
            (staging / "pm2_jlist.json").write_text(
                pm2_detail or "[]", encoding="utf-8"
            )

            # 3. Copy .env files
            env_staging = staging / "envs"
            env_staging.mkdir(exist_ok=True)
            env_manifest = []
            for env_path in ENV_PATHS:
                if env_path.exists():
                    safe_name = str(env_path).replace("/", "_").lstrip("_") + ".env"
                    dest = env_staging / safe_name
                    try:
                        shutil.copy2(env_path, dest)
                        env_manifest.append({"original": str(env_path), "saved_as": safe_name})
                        log.info(f"Snapshot: kopiert {env_path}")
                    except OSError as copy_err:
                        log.warning(f"Snapshot: übersprungen (EPERM/iCloud) {env_path}: {copy_err}")
                else:
                    log.debug(f"Snapshot: .env nicht gefunden: {env_path}")
            (staging / "env_manifest.json").write_text(
                json.dumps(env_manifest, indent=2), encoding="utf-8"
            )

            # 4. ecosystem.config.js
            if ECOSYSTEM_PATH.exists():
                shutil.copy2(ECOSYSTEM_PATH, staging / "ecosystem.config.js")

            # 5. Snapshot metadata
            meta = {
                "created_at": datetime.now().isoformat(),
                "hostname": os.uname().nodename,
                "base_dir": str(BASE_DIR),
                "env_files_count": len(env_manifest),
                "archive": archive_name,
            }
            (staging / "meta.json").write_text(
                json.dumps(meta, indent=2), encoding="utf-8"
            )

            # 6. Create tar.gz
            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(staging, arcname=f"rudiclone_{ts}")

            log.info(f"Snapshot erstellt: {archive_path} ({archive_path.stat().st_size // 1024} KB)")
            return str(archive_path)

        except Exception as exc:
            log.error(f"snapshot Exception: {exc}")
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    async def restore(self, snapshot_path: str, apply: bool = False) -> bool:
        path = Path(snapshot_path)
        if not path.exists():
            log.error(f"restore: Snapshot nicht gefunden: {snapshot_path}")
            return False

        extract_dir = self.backups_dir / f"restore_preview_{datetime.now().strftime('%H%M%S')}"

        try:
            extract_dir.mkdir(parents=True, exist_ok=True)
            with tarfile.open(path, "r:gz") as tar:
                tar.extractall(extract_dir)

            # Find top-level dir in archive
            extracted_dirs = [d for d in extract_dir.iterdir() if d.is_dir()]
            if not extracted_dirs:
                log.error("restore: Kein Verzeichnis im Archiv gefunden")
                return False
            content_dir = extracted_dirs[0]

            # Read meta
            meta_file = content_dir / "meta.json"
            meta = {}
            if meta_file.exists():
                meta = json.loads(meta_file.read_text())
                log.info(f"restore: Snapshot vom {meta.get('created_at', '?')}")

            # Read env manifest
            manifest_file = content_dir / "env_manifest.json"
            env_manifest = []
            if manifest_file.exists():
                env_manifest = json.loads(manifest_file.read_text())

            if not apply:
                # DRY-RUN: just report what would happen
                report = {
                    "dry_run": True,
                    "snapshot": str(path),
                    "meta": meta,
                    "would_restore_envs": [e["original"] for e in env_manifest],
                    "ecosystem_present": (content_dir / "ecosystem.config.js").exists(),
                    "pm2_snapshot_present": (content_dir / "pm2_list.json").exists(),
                    "message": "Dry-run — übergib apply=True um wirklich wiederherzustellen",
                }
                log.info(f"Restore Dry-Run: {json.dumps(report, indent=2)}")
                return True

            # APPLY: actually restore
            env_dir = content_dir / "envs"
            restored = []
            for entry in env_manifest:
                src = env_dir / entry["saved_as"]
                dest = Path(entry["original"])
                if src.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    restored.append(str(dest))
                    log.info(f"restore: Wiederhergestellt {dest}")

            eco_src = content_dir / "ecosystem.config.js"
            if eco_src.exists():
                shutil.copy2(eco_src, ECOSYSTEM_PATH)
                log.info(f"restore: ecosystem.config.js wiederhergestellt")

            log.info(
                f"Restore abgeschlossen: {len(restored)} .env-Dateien, "
                f"ecosystem.config.js={'ja' if eco_src.exists() else 'nein'}"
            )
            return True

        except Exception as exc:
            log.error(f"restore Exception: {exc}")
            return False
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)

    def list_snapshots(self) -> List[Dict[str, Any]]:
        snapshots = []
        try:
            for f in sorted(self.backups_dir.glob("rudiclone_*.tar.gz"), reverse=True):
                stat = f.stat()
                snapshots.append({
                    "path": str(f),
                    "name": f.name,
                    "size_kb": stat.st_size // 1024,
                    "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
        except Exception as exc:
            log.error(f"list_snapshots Exception: {exc}")
        return snapshots

    async def diff(self, snapshot_path: str) -> Dict[str, Any]:
        path = Path(snapshot_path)
        if not path.exists():
            return {"error": f"Snapshot nicht gefunden: {snapshot_path}"}

        extract_dir = self.backups_dir / f"diff_tmp_{datetime.now().strftime('%H%M%S')}"
        try:
            extract_dir.mkdir(parents=True, exist_ok=True)
            with tarfile.open(path, "r:gz") as tar:
                tar.extractall(extract_dir)

            extracted_dirs = [d for d in extract_dir.iterdir() if d.is_dir()]
            if not extracted_dirs:
                return {"error": "Kein Verzeichnis im Archiv"}
            content_dir = extracted_dirs[0]

            changes: Dict[str, Any] = {
                "snapshot": str(path),
                "checked_at": datetime.now().isoformat(),
                "env_changes": [],
                "ecosystem_changed": False,
                "pm2_changes": [],
            }

            # Check .env changes
            manifest_file = content_dir / "env_manifest.json"
            if manifest_file.exists():
                env_manifest = json.loads(manifest_file.read_text())
                env_dir = content_dir / "envs"
                for entry in env_manifest:
                    saved_src = env_dir / entry["saved_as"]
                    current = Path(entry["original"])
                    if not saved_src.exists():
                        continue
                    if not current.exists():
                        changes["env_changes"].append({
                            "file": entry["original"],
                            "status": "missing_now",
                        })
                        continue
                    saved_content = saved_src.read_text(errors="replace")
                    current_content = current.read_text(errors="replace")
                    if saved_content != current_content:
                        # Find changed keys (non-secret diff)
                        saved_keys = set(
                            l.split("=")[0].strip()
                            for l in saved_content.splitlines()
                            if "=" in l and not l.startswith("#")
                        )
                        curr_keys = set(
                            l.split("=")[0].strip()
                            for l in current_content.splitlines()
                            if "=" in l and not l.startswith("#")
                        )
                        added = list(curr_keys - saved_keys)
                        removed = list(saved_keys - curr_keys)
                        changes["env_changes"].append({
                            "file": entry["original"],
                            "status": "changed",
                            "keys_added": added,
                            "keys_removed": removed,
                        })

            # Check ecosystem.config.js
            eco_saved = content_dir / "ecosystem.config.js"
            if eco_saved.exists() and ECOSYSTEM_PATH.exists():
                if eco_saved.read_text() != ECOSYSTEM_PATH.read_text():
                    changes["ecosystem_changed"] = True

            # Check PM2 changes
            pm2_saved_file = content_dir / "pm2_list.json"
            if pm2_saved_file.exists():
                try:
                    saved_pm2 = json.loads(pm2_saved_file.read_text())
                    current_pm2_raw = await self._run_cmd(["pm2", "jlist"])
                    current_pm2 = json.loads(current_pm2_raw or "[]")
                    saved_names = {
                        p.get("name") for p in (saved_pm2 if isinstance(saved_pm2, list) else [])
                    }
                    current_names = {
                        p.get("name") for p in (current_pm2 if isinstance(current_pm2, list) else [])
                    }
                    added_procs = list(current_names - saved_names)
                    removed_procs = list(saved_names - current_names)
                    if added_procs or removed_procs:
                        changes["pm2_changes"] = {
                            "added": added_procs,
                            "removed": removed_procs,
                        }
                except Exception as exc:
                    log.warning(f"diff PM2 comparison failed: {exc}")

            return changes

        except Exception as exc:
            log.error(f"diff Exception: {exc}")
            return {"error": str(exc)}
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)

    @staticmethod
    async def _run_cmd(cmd: List[str]) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            return stdout.decode("utf-8", errors="replace").strip()
        except asyncio.TimeoutError:
            log.warning(f"Kommando Timeout: {' '.join(cmd)}")
            return ""
        except FileNotFoundError:
            log.warning(f"Kommando nicht gefunden: {cmd[0]}")
            return ""
        except Exception as exc:
            log.error(f"_run_cmd {cmd}: {exc}")
            return ""


# ===========================================================================
# C — RudiAgents (Sub-Agent Orchestration)
# ===========================================================================

AGENT_NAMES = ["SystemDiagnoseAgent", "ShopifyAgent", "TradeAgent", "LoadMonitor"]

LOAD_ALERT_THRESHOLD   = 20.0
PM2_RESTART_THRESHOLD  = 5
TRADE_ALERT_PCT        = 2.0   # percent price move to alert


class _AgentState:
    def __init__(self, name: str):
        self.name = name
        self.last_run: Optional[str] = None
        self.last_result: Optional[Dict] = None
        self.error_count: int = 0
        self.task: Optional[asyncio.Task] = None


class RudiAgents:
    def __init__(self):
        self._states: Dict[str, _AgentState] = {
            name: _AgentState(name) for name in AGENT_NAMES
        }
        self._price_cache: Dict[str, float] = {}
        # tracks last-seen PM2 restart counts → only alert on NEW restarts
        self._pm2_restart_baseline: Dict[str, int] = {}
        # how many NEW restarts in one cycle triggers an alert
        self._pm2_new_restart_threshold: int = 3

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_all(self) -> None:
        log.info("RudiAgents: Starte alle Agenten...")
        self._states["SystemDiagnoseAgent"].task = asyncio.create_task(
            self._loop_agent("SystemDiagnoseAgent", self._system_diagnose, 60),
            name="SystemDiagnoseAgent",
        )
        self._states["ShopifyAgent"].task = asyncio.create_task(
            self._loop_agent("ShopifyAgent", self._shopify_check, 300),
            name="ShopifyAgent",
        )
        self._states["TradeAgent"].task = asyncio.create_task(
            self._loop_agent("TradeAgent", self._trade_check, 120),
            name="TradeAgent",
        )
        self._states["LoadMonitor"].task = asyncio.create_task(
            self._loop_agent("LoadMonitor", self._load_monitor, 30),
            name="LoadMonitor",
        )
        log.info("RudiAgents: Alle 4 Agenten gestartet (Madafaka!)")

    async def stop_all(self) -> None:
        log.info("RudiAgents: Stoppe alle Agenten...")
        for state in self._states.values():
            if state.task and not state.task.done():
                state.task.cancel()
                try:
                    await asyncio.wait_for(asyncio.shield(state.task), timeout=5)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
        log.info("RudiAgents: Alle Agenten gestoppt")

    async def get_status(self) -> Dict[str, Any]:
        status = {}
        for name, state in self._states.items():
            status[name] = {
                "last_run": state.last_run,
                "last_result": state.last_result,
                "error_count": state.error_count,
                "running": (
                    state.task is not None
                    and not state.task.done()
                ),
            }
        return status

    async def run_once(self, agent_name: str) -> Dict[str, Any]:
        handlers = {
            "SystemDiagnoseAgent": self._system_diagnose,
            "ShopifyAgent": self._shopify_check,
            "TradeAgent": self._trade_check,
            "LoadMonitor": self._load_monitor,
        }
        if agent_name not in handlers:
            return {"error": f"Unbekannter Agent: {agent_name}. Verfügbar: {list(handlers.keys())}"}
        return await self._run_agent(agent_name, handlers[agent_name])

    # ------------------------------------------------------------------
    # Loop wrapper
    # ------------------------------------------------------------------

    async def _loop_agent(
        self, name: str, handler, interval_sec: int
    ) -> None:
        log.info(f"[{name}] Loop gestartet (interval={interval_sec}s)")
        while True:
            await self._run_agent(name, handler)
            await asyncio.sleep(interval_sec)

    async def _run_agent(self, name: str, handler) -> Dict[str, Any]:
        state = self._states[name]
        try:
            result = await handler()
            state.last_run = datetime.now().isoformat()
            state.last_result = result
            return result
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state.error_count += 1
            state.last_run = datetime.now().isoformat()
            err = {"error": str(exc), "agent": name}
            state.last_result = err
            log.error(f"[{name}] Exception: {exc}")
            return err

    # ------------------------------------------------------------------
    # Agent: SystemDiagnoseAgent (every 60s)
    # ------------------------------------------------------------------

    async def _system_diagnose(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"agent": "SystemDiagnoseAgent", "ts": datetime.now().isoformat()}
        alerts = []

        # Load average
        try:
            load1, load5, load15 = os.getloadavg()
            result["load"] = {"1m": load1, "5m": load5, "15m": load15}
            if load1 > LOAD_ALERT_THRESHOLD:
                alerts.append(f"LOAD CRITICAL: {load1:.1f} (1m avg)")
        except Exception as exc:
            result["load_error"] = str(exc)

        # Top CPU/MEM processes
        try:
            ps_out = subprocess.check_output(
                ["ps", "aux", "-r"],
                stderr=subprocess.DEVNULL,
                timeout=10,
            ).decode("utf-8", errors="replace")
            lines = ps_out.strip().splitlines()
            top_procs = []
            for line in lines[1:6]:  # skip header, take top 5
                parts = line.split(None, 10)
                if len(parts) >= 11:
                    top_procs.append({
                        "pid": parts[1],
                        "cpu": parts[2],
                        "mem": parts[3],
                        "cmd": parts[10][:60],
                    })
            result["top_processes"] = top_procs
        except Exception as exc:
            result["ps_error"] = str(exc)

        # Disk space
        try:
            df_out = subprocess.check_output(
                ["df", "-h", "/"],
                stderr=subprocess.DEVNULL,
                timeout=10,
            ).decode("utf-8", errors="replace")
            lines = df_out.strip().splitlines()
            if len(lines) >= 2:
                parts = lines[1].split()
                result["disk"] = {
                    "total": parts[1] if len(parts) > 1 else "?",
                    "used": parts[2] if len(parts) > 2 else "?",
                    "avail": parts[3] if len(parts) > 3 else "?",
                    "use_pct": parts[4] if len(parts) > 4 else "?",
                }
                use_str = result["disk"]["use_pct"].replace("%", "")
                try:
                    if int(use_str) >= 90:
                        alerts.append(f"DISK WARNING: {result['disk']['use_pct']} verwendet")
                except ValueError:
                    pass
        except Exception as exc:
            result["disk_error"] = str(exc)

        # PM2 restart counts — alert only on NEW restarts since last check
        try:
            proc = await asyncio.create_subprocess_exec(
                "pm2", "jlist",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            pm2_list = json.loads(stdout.decode("utf-8", errors="replace") or "[]")
            restarts_info = []
            new_crash_alerts = []
            for app in pm2_list:
                name = app.get("name", "?")
                restarts = app.get("pm2_env", {}).get("restart_time", 0)
                status = app.get("pm2_env", {}).get("status", "?")
                restarts_info.append({"name": name, "restarts": restarts, "status": status})

                baseline = self._pm2_restart_baseline.get(name)
                if baseline is None:
                    # First run — record baseline, no alert (avoids spam on startup)
                    self._pm2_restart_baseline[name] = restarts
                else:
                    delta = restarts - baseline
                    if delta >= self._pm2_new_restart_threshold:
                        new_crash_alerts.append(
                            f"PM2 CRASH-LOOP: {name} +{delta} Neustarts (total: {restarts})"
                        )
                        # Update baseline so next check is relative to now
                        self._pm2_restart_baseline[name] = restarts
                    elif delta > 0:
                        # Small increment — update baseline silently
                        self._pm2_restart_baseline[name] = restarts

                # Always alert if process is in errored state
                if status == "errored":
                    alerts.append(f"PM2 ERRORED: {name} ist im Fehlerzustand!")

            alerts.extend(new_crash_alerts)
            result["pm2"] = restarts_info
        except (FileNotFoundError, asyncio.TimeoutError) as exc:
            result["pm2_error"] = str(exc)
        except Exception as exc:
            result["pm2_error"] = str(exc)

        result["alerts"] = alerts

        # Send Telegram if alerts
        if alerts:
            msg = "🚨 <b>RudiClone SystemDiagnose Alert</b>\n\n" + "\n".join(
                f"• {a}" for a in alerts
            )
            await send_telegram(msg)
            log.warning(f"SystemDiagnose Alerts gesendet: {alerts}")

        return result

    # ------------------------------------------------------------------
    # Agent: ShopifyAgent (every 300s)
    # ------------------------------------------------------------------

    async def _shopify_check(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"agent": "ShopifyAgent", "ts": datetime.now().isoformat()}

        if not SHOPIFY_STORE_URL or not SHOPIFY_ACCESS_TOK:
            result["status"] = "skipped"
            result["reason"] = "SHOPIFY_STORE_URL oder SHOPIFY_ACCESS_TOKEN nicht gesetzt"
            return result

        url = SHOPIFY_STORE_URL.rstrip("/") + "/admin/api/2024-10/shop.json"
        headers = {
            "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOK,
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=20)
            ) as session:
                async with session.get(url, headers=headers) as resp:
                    result["http_status"] = resp.status
                    if resp.status == 200:
                        data = await resp.json()
                        shop = data.get("shop", {})
                        result["status"] = "ok"
                        result["store_name"] = shop.get("name", "?")
                        result["plan"] = shop.get("plan_name", "?")
                        result["domain"] = shop.get("domain", "?")
                        log.info(f"ShopifyAgent: Store OK — {result['store_name']}")
                    elif resp.status == 401:
                        result["status"] = "auth_error"
                        result["error"] = "401 — Token abgelaufen oder ungültig!"
                        await send_telegram(
                            "⚠️ <b>Shopify Token abgelaufen!</b>\n"
                            "SHOPIFY_ACCESS_TOKEN muss erneuert werden. kruzufix."
                        )
                        log.error("ShopifyAgent: 401 — Token ungültig!")
                    else:
                        body = await resp.text()
                        result["status"] = "error"
                        result["error"] = f"HTTP {resp.status}: {body[:200]}"
                        log.warning(f"ShopifyAgent: HTTP {resp.status}")
        except asyncio.TimeoutError:
            result["status"] = "timeout"
            result["error"] = "Request Timeout nach 20s"
            log.warning("ShopifyAgent: Timeout")
        except Exception as exc:
            result["status"] = "exception"
            result["error"] = str(exc)
            log.error(f"ShopifyAgent Exception: {exc}")

        return result

    # ------------------------------------------------------------------
    # Agent: TradeAgent (every 120s)
    # ------------------------------------------------------------------

    async def _trade_check(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"agent": "TradeAgent", "ts": datetime.now().isoformat()}
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        prices: Dict[str, float] = {}
        alerts = []

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)
            ) as session:
                for symbol in symbols:
                    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
                    try:
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                price = float(data.get("price", 0))
                                prices[symbol] = price

                                # Compare with cached price
                                prev = self._price_cache.get(symbol)
                                if prev and prev > 0:
                                    change_pct = abs((price - prev) / prev) * 100
                                    direction = "📈" if price > prev else "📉"
                                    if change_pct >= TRADE_ALERT_PCT:
                                        alerts.append(
                                            f"{direction} {symbol}: {prev:.2f} → {price:.2f} "
                                            f"({change_pct:+.2f}%)"
                                        )
                            else:
                                log.warning(f"TradeAgent: {symbol} HTTP {resp.status}")
                    except Exception as exc:
                        log.warning(f"TradeAgent {symbol} Exception: {exc}")
                        prices[symbol] = self._price_cache.get(symbol, 0.0)

        except Exception as exc:
            result["error"] = str(exc)
            log.error(f"TradeAgent session Exception: {exc}")

        # Update cache
        self._price_cache.update(prices)
        result["prices"] = prices
        result["alerts"] = alerts

        if alerts:
            msg = "💰 <b>RudiClone Trade Alert</b>\n\n" + "\n".join(alerts)
            await send_telegram(msg)
            log.info(f"TradeAgent Alerts: {alerts}")

        return result

    # ------------------------------------------------------------------
    # Agent: LoadMonitor (every 30s)
    # ------------------------------------------------------------------

    async def _load_monitor(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"agent": "LoadMonitor", "ts": datetime.now().isoformat()}
        killed = []

        try:
            load1, load5, _ = os.getloadavg()
            result["load_1m"] = load1
            result["load_5m"] = load5

            # Kill zombie `top` processes
            try:
                pgrep_out = subprocess.check_output(
                    ["pgrep", "-l", "top"],
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                ).decode("utf-8", errors="replace").strip()
                if pgrep_out:
                    for line in pgrep_out.splitlines():
                        parts = line.split(None, 1)
                        if len(parts) >= 2 and "top" in parts[1]:
                            pid = int(parts[0])
                            # Only kill if process has been running strangely long (zombie check)
                            try:
                                # Check if it's a background/zombie top
                                stat_out = subprocess.check_output(
                                    ["ps", "-p", str(pid), "-o", "stat="],
                                    stderr=subprocess.DEVNULL,
                                    timeout=3,
                                ).decode().strip()
                                if "Z" in stat_out or "T" in stat_out:
                                    os.kill(pid, 9)
                                    killed.append(pid)
                                    log.info(f"LoadMonitor: Zombie top PID {pid} gekillt")
                            except (ProcessLookupError, subprocess.CalledProcessError):
                                pass
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass  # no top processes

            result["killed_zombies"] = killed

        except Exception as exc:
            result["error"] = str(exc)
            log.error(f"LoadMonitor Exception: {exc}")

        return result


# ===========================================================================
# Main entrypoint
# ===========================================================================

async def _main() -> None:
    log.info("=" * 60)
    log.info("RudiClone gestartet — alle Agenten laufen")
    log.info("=" * 60)

    agents = RudiAgents()
    await agents.start_all()

    try:
        # Keep running until interrupted
        while True:
            await asyncio.sleep(60)
            status = await agents.get_status()
            for name, info in status.items():
                log.info(
                    f"[{name}] last_run={info['last_run']} "
                    f"errors={info['error_count']} running={info['running']}"
                )
    except (KeyboardInterrupt, asyncio.CancelledError):
        log.info("RudiClone: Shutdown Signal empfangen")
    finally:
        await agents.stop_all()
        log.info("RudiClone: Sauber beendet. Tschüss Madafaka!")


async def get_status() -> dict:
    """Module-level status function for dashboard handler."""
    return {
        "ok": True,
        "status": "active",
        "module": "rudiclone",
        "agents": ["SystemDiagnoseAgent", "ShopifyAgent", "TradeAgent", "LoadMonitor"],
        "modes": ["RudiPersona", "RudiSystemClone", "RudiAgents"],
    }


if __name__ == "__main__":
    asyncio.run(_main())
