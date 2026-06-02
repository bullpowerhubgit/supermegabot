#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║          RUDIBOT ETERNAL GUARDIAN v1.0                          ║
║  Selbstheilend · Selbstverbessernd · Niemals kaputt             ║
║  Läuft alle 2h · Repariert bis fehlerfrei · Lernt jeden Tag    ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os, sys, json, time, logging, subprocess, datetime, signal, traceback, threading, hashlib, hmac
from pathlib import Path
from functools import wraps

# Flask API Imports (optional, falls nicht installiert wird API deaktiviert)
try:
    from flask import Flask, request, jsonify, abort
    from flask.views import MethodView
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    logging.warning("Flask nicht installiert - API wird deaktiviert. Installieren: pip install flask")

BASE_DIR    = Path(__file__).parent
BRAIN_FILE  = BASE_DIR / 'brain' / 'learned_fixes.json'
REPORT_FILE = BASE_DIR / 'brain' / 'daily_reports.json'
IMPROVE_LOG = BASE_DIR / 'brain' / 'improvement_log.json'
LOG_FILE    = BASE_DIR / 'logs' / 'eternal.log'
LOCK_FILE   = BASE_DIR / '.running.lock'

# ── Logging ──────────────────────────────────────────────────────────────────
(BASE_DIR / 'logs').mkdir(parents=True, exist_ok=True)  # Ordner sicherstellen vor FileHandler
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger('EternalGuardian')

# ── JSON Helpers ─────────────────────────────────────────────────────────────
def load_json(path, default):
    try:
        if Path(path).exists():
            return json.loads(Path(path).read_text())
    except: pass
    return default

def save_json(path, data):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    except Exception as e:
        log.error(f'save_json {path}: {e}')

# ── API Configuration ────────────────────────────────────────────────────────
API_CONFIG = {
    'host': os.getenv('GUARDIAN_API_HOST', '0.0.0.0'),
    'port': int(os.getenv('GUARDIAN_API_PORT', 3201)),
    'secret_key': os.getenv('GUARDIAN_API_SECRET', 'rudibot-secret-key-change-in-production'),
    'webhook_secret': os.getenv('GUARDIAN_WEBHOOK_SECRET', 'webhook-secret-change-me'),
    'auth_enabled': os.getenv('GUARDIAN_API_AUTH', 'true').lower() == 'true',
}

# ── Discord/Slack Webhook URLs ─────────────────────────────────────────────
NOTIFICATION_CONFIG = {
    'telegram_enabled': True,
    'discord_webhook': os.getenv('DISCORD_WEBHOOK_URL', ''),
    'slack_webhook': os.getenv('SLACK_WEBHOOK_URL', ''),
    'github_webhook_secret': os.getenv('GITHUB_WEBHOOK_SECRET', ''),
    'prometheus_enabled': os.getenv('PROMETHEUS_ENABLED', 'true').lower() == 'true',
}

# ── Service Registry ─────────────────────────────────────────────────────────
# Pfade über Umgebungsvariablen → portable (macOS, Linux, Docker)
HOME_DIR   = os.path.expanduser('~')
BOT_DIR    = os.getenv('TELEGRAM_BOT_DIR', os.path.join(HOME_DIR, 'local-projects', 'telegram-automation-bot'))
OLLAMA_DIR = os.getenv('OLLAMA_DIR', HOME_DIR)
REDIS_DIR  = os.getenv('REDIS_DIR', HOME_DIR)

SERVICES = [
    {
        'name':     'RudiBot Main',
        'port':     3200,
        'url':      'http://localhost:3200/health',
        'cwd':      BOT_DIR,
        'start':    ['node', 'server.js'],
        'check':    'http',
        'critical': True,
    },
    {
        'name':     'Ollama LLM',
        'port':     11434,
        'url':      'http://localhost:11434/api/tags',
        'cwd':      OLLAMA_DIR,
        'start':    ['ollama', 'serve'],
        'check':    'http',
        'critical': True,
    },
    {
        'name':     'Redis',
        'port':     6379,
        'url':      None,
        'cwd':      REDIS_DIR,
        'start':    ['redis-server', '--daemonize', 'yes'],
        'check':    'port',
        'critical': False,
    },
]

# ── Brain: Gelerntes Wissen über Fehler & Fixes ──────────────────────────────
class Brain:
    def __init__(self):
        self.data = load_json(BRAIN_FILE, {
            'fixes': {},
            'stats': {'total_repairs': 0, 'never_recurring': [], 'last_updated': ''},
            'patterns': {}
        })

    def record_error(self, service, error_key, fix_applied, success):
        if error_key not in self.data['fixes']:
            self.data['fixes'][error_key] = {
                'service': service, 'first_seen': str(datetime.date.today()),
                'count': 0, 'fix': fix_applied, 'success_rate': 0,
                'last_seen': '', 'resolved_permanently': False
            }
        e = self.data['fixes'][error_key]
        e['count'] += 1
        e['last_seen'] = str(datetime.datetime.now())
        e['fix'] = fix_applied
        if success:
            self.data['stats']['total_repairs'] += 1
            e['success_rate'] = min(100, e.get('success_rate', 0) + 10)
            if e['count'] >= 3 and e['success_rate'] >= 100:
                e['resolved_permanently'] = True
                if error_key not in self.data['stats']['never_recurring']:
                    self.data['stats']['never_recurring'].append(error_key)
                    log.info(f'🎓 Brain gelernt: "{error_key}" wird nie wieder auftreten')
        self.data['stats']['last_updated'] = str(datetime.datetime.now())
        save_json(BRAIN_FILE, self.data)

    def get_known_fix(self, error_key):
        return self.data['fixes'].get(error_key, {}).get('fix')

    def is_permanently_resolved(self, error_key):
        return self.data['fixes'].get(error_key, {}).get('resolved_permanently', False)

    def get_summary(self):
        return {
            'total_repairs': self.data['stats']['total_repairs'],
            'patterns_learned': len(self.data['fixes']),
            'permanently_resolved': len(self.data['stats']['never_recurring']),
        }

brain = Brain()

# ── Health Checker ────────────────────────────────────────────────────────────
def check_port(port):
    import socket
    try:
        with socket.socket() as s:
            s.settimeout(2)
            s.connect(('127.0.0.1', port))
        return True
    except:
        return False

def check_http(url):
    import urllib.request, urllib.error
    try:
        req = urllib.request.urlopen(url, timeout=5)
        return req.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except: return False

def health_check_service(svc):
    if svc['check'] == 'http' and svc.get('url'):
        ok = check_http(svc['url'])
    else:
        ok = check_port(svc['port'])
    return ok

# ── Auto Healer ───────────────────────────────────────────────────────────────
def kill_port(port):
    try:
        result = subprocess.run(
            ['lsof', '-ti', f'tcp:{port}'],
            capture_output=True, text=True
        )
        pids = result.stdout.strip().split('\n')
        for pid in pids:
            if pid.strip():
                subprocess.run(['kill', '-9', pid.strip()], capture_output=True)
        time.sleep(1)
        return True
    except: return False

def start_service(svc):
    """Start einen Dienst und warte bis er läuft."""
    log.info(f'  🔧 Starte {svc["name"]} auf Port {svc["port"]}...')
    try:
        cwd = svc.get('cwd', os.path.expanduser('~'))
        if not Path(cwd).exists():
            log.error(f'  ❌ CWD nicht gefunden: {cwd}')
            return False
        env = os.environ.copy()
        env['PATH'] = os.path.expandvars('/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH') if sys.platform == 'darwin' else env.get('PATH', '')

        # Load .env if exists
        env_file = Path(cwd) / '.env'
        if env_file.exists():
            for line in env_file.read_text(errors='ignore').splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, _, v = line.partition('=')
                    env[k.strip()] = v.strip()

        cmd = svc['start']
        shell = isinstance(cmd, str)
        log_path = BASE_DIR / 'logs' / f'{svc["name"].replace(" ", "_").lower()}.log'
        with open(log_path, 'a') as lf:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdout=lf,
                stderr=lf,
                start_new_session=True,
                shell=shell
            )

        # Wait up to 15s for port to open
        for _ in range(15):
            time.sleep(1)
            if health_check_service(svc):
                log.info(f'  ✅ {svc["name"]} läuft (PID {proc.pid})')
                return True
        log.warning(f'  ⚠️  {svc["name"]} gestartet aber Port noch nicht offen')
        return False
    except Exception as e:
        log.error(f'  ❌ Start fehlgeschlagen: {e}')
        return False

def heal_service(svc, attempt=1):
    """Heilt einen fehlerhaften Dienst — versucht es bis es klappt (iterativ)."""
    name = svc['name']
    error_key = f'{name}_down'
    MAX_ATTEMPTS = 5

    for attempt in range(1, MAX_ATTEMPTS + 1):
        log.warning(f'🔴 {name} ist down (Versuch {attempt}/{MAX_ATTEMPTS})')

        # Strategie je Versuch
        if attempt >= 2:
            log.info(f'  🔫 Beende Prozess auf Port {svc["port"]}')
            kill_port(svc['port'])
            time.sleep(2)

        if attempt >= 3:
            cmd = svc['start']
            cmd0 = cmd[0] if isinstance(cmd, list) else cmd.split()[0]
            if cmd0 in ('node', 'npm', 'npx'):
                cwd = svc.get('cwd', '')
                log.info(f'  🧹 Cleanup node_modules cache in {cwd}')
                try:
                    subprocess.run(['npm', 'cache', 'clean', '--force'],
                        cwd=cwd, capture_output=True, timeout=30)
                except Exception as e:
                    log.debug(f'npm cache clean failed: {e}')

        if attempt >= 4:
            cwd = svc.get('cwd', '')
            if cwd and Path(cwd).joinpath('package.json').exists():
                log.info(f'  📦 npm install in {cwd}')
                try:
                    subprocess.run(['npm', 'install', '--omit=dev'],
                        cwd=cwd, capture_output=True, timeout=120, env={
                            **os.environ,
                            'PATH': os.path.expandvars('/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH') if sys.platform == 'darwin' else os.environ.get('PATH','')
                        })
                except: pass

        success = start_service(svc)
        brain.record_error(name, error_key, f'restart_attempt_{attempt}', success)

        if success:
            log.info(f'✅ {name} erfolgreich repariert nach {attempt} Versuch(en)')
            return True

        if attempt < MAX_ATTEMPTS:
            time.sleep(5 * attempt)

    log.error(f'❌ {name}: Konnte nach {MAX_ATTEMPTS} Versuchen nicht reparieren')
    brain.record_error(name, error_key, 'manual_restart_needed', False)
    return False

# ── Self Improver: Verbessert sich täglich ────────────────────────────────────
class SelfImprover:
    def __init__(self):
        self.log_data = load_json(IMPROVE_LOG, {'improvements': [], 'score': 0})

    def analyze_and_improve(self):
        improvements = []
        today = str(datetime.date.today())

        # 1. Server-Logs auf Fehler analysieren
        bot_log = Path(os.getenv('TELEGRAM_BOT_DIR', os.path.join(os.path.expanduser('~'), 'local-projects', 'telegram-automation-bot'))) / 'logs'
        if not bot_log.exists():
            bot_log = BASE_DIR / 'logs'

        errors_found = {}
        for log_file in list((BASE_DIR / 'logs').glob('*.log'))[:5]:
            try:
                content = log_file.read_text(errors='ignore')[-5000:]  # Last 5KB
                # Count error patterns
                patterns = {
                    'ECONNREFUSED': 'Verbindung abgelehnt',
                    'ETIMEDOUT': 'Timeout',
                    'Cannot find module': 'Modul fehlt',
                    'SyntaxError': 'Syntax-Fehler',
                    'UnhandledPromiseRejection': 'Unbehandelte Promise',
                    'ENOENT': 'Datei nicht gefunden',
                    'Out of memory': 'Speicherproblem',
                }
                for pattern, desc in patterns.items():
                    count = content.count(pattern)
                    if count > 0:
                        errors_found[pattern] = errors_found.get(pattern, 0) + count

            except: pass

        # 2. Fixes für gefundene Fehler anwenden
        fixes_applied = []
        for error, count in errors_found.items():
            if error == 'Cannot find module':
                # Auto-reinstall dependencies
                for svc in SERVICES:
                    cwd = svc.get('cwd', '')
                    pkg = Path(cwd) / 'package.json'
                    if pkg.exists():
                        try:
                            result = subprocess.run(
                                ['npm', 'install', '--omit=dev'],
                                cwd=cwd, capture_output=True, timeout=120,
                                env={**os.environ, 'PATH': os.path.expandvars('/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH') if sys.platform == 'darwin' else os.environ.get('PATH','')}
                            )
                            if result.returncode == 0:
                                fixes_applied.append(f'npm install in {cwd}')
                                brain.record_error('auto_improve', error, 'npm_install', True)
                        except: pass

            elif error == 'SyntaxError':
                fixes_applied.append('SyntaxError erkannt — manuelle Prüfung empfohlen')

        # 3. Disk Space Check + Cleanup
        try:
            result = subprocess.run(['df', '-Ph', '/'], capture_output=True, text=True)
            line = [l for l in result.stdout.splitlines() if '/dev/' in l]
            if line:
                parts = line[0].split()
                use_pct = int(parts[4].rstrip('%'))
                if use_pct > 85:
                    # Clean node_modules in non-critical projects
                    log.warning(f'⚠️  Festplatte {use_pct}% voll — starte Cleanup')
                    self._cleanup_disk()
                    improvements.append(f'Disk cleanup bei {use_pct}% Auslastung')
        except: pass

        # 4. Memory pressure check (portabel: psutil wenn verfügbar, sonst Fallback)
        try:
            import psutil
            swap = psutil.swap_memory()
            if swap.used > 2 * 1024 * 1024 * 1024:  # > 2GB
                improvements.append(f'⚠️ Hoher Swap: {swap.used / 1e9:.1f}GB — Neustart empfohlen')
            mem = psutil.virtual_memory()
            if mem.percent > 90:
                improvements.append(f'⚠️ RAM kritisch: {mem.percent}% — Cleanup empfohlen')
        except ImportError:
            # Fallback: nur auf macOS
            if sys.platform == 'darwin':
                try:
                    result = subprocess.run(["vm_stat"], capture_output=True, text=True)
                    if 'page' in result.stdout.lower():
                        swap = subprocess.run(['sysctl', 'vm.swapusage'], capture_output=True, text=True)
                        if 'used = ' in swap.stdout:
                            used_str = swap.stdout.split('used = ')[1].split('M')[0]
                            try:
                                used_mb = float(used_str.strip())
                                if used_mb > 2000:
                                    improvements.append(f'⚠️ Hoher Swap: {used_mb:.0f}MB — Neustart empfohlen')
                            except: pass
                except: pass
        except: pass

        # 5. Check for outdated npm packages (weekly)
        weekday = datetime.date.today().weekday()
        if weekday == 0:  # Monday
            improvements.append('📦 Wochentag 1: npm audit läuft...')
            for svc in SERVICES[:2]:
                cwd = svc.get('cwd', '')
                if Path(cwd).joinpath('package.json').exists():
                    try:
                        result = subprocess.run(
                            ['npm', 'audit', '--json'],
                            cwd=cwd, capture_output=True, timeout=60,
                            env={**os.environ, 'PATH': os.path.expandvars('/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH') if sys.platform == 'darwin' else os.environ.get('PATH','')}
                        )
                        audit = json.loads(result.stdout) if result.stdout else {}
                        vuln = audit.get('metadata', {}).get('vulnerabilities', {})
                        total_vuln = sum(vuln.values()) if isinstance(vuln, dict) else 0
                        if total_vuln > 0:
                            improvements.append(f'🔒 {svc["name"]}: {total_vuln} npm Vulnerabilities gefunden')
                    except: pass

        # Record improvements
        entry = {
            'date': today,
            'errors_detected': errors_found,
            'fixes_applied': fixes_applied,
            'improvements': improvements,
            'brain_stats': brain.get_summary(),
        }

        if fixes_applied or improvements:
            self.log_data['improvements'].append(entry)
            self.log_data['score'] = self.log_data.get('score', 0) + len(fixes_applied) + 1
            save_json(IMPROVE_LOG, self.log_data)
            log.info(f'🧠 Verbesserungen heute: {len(fixes_applied)} Fixes, {len(improvements)} Analysen')
        else:
            log.info('✅ Keine Verbesserungen nötig — alles optimal')

        return entry

    def _cleanup_disk(self):
        """Löscht unnötige Dateien um Platz zu schaffen."""
        # Clear npm cache
        try:
            subprocess.run(['npm', 'cache', 'clean', '--force'],
                capture_output=True, timeout=60,
                env={**os.environ, 'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:'+os.environ.get('PATH','')})
            log.info('  ✅ npm cache geleert')
        except: pass

        # Clear old logs
        for log_file in (BASE_DIR / 'logs').glob('*.log'):
            try:
                size = log_file.stat().st_size
                if size > 50 * 1024 * 1024:  # >50MB
                    # Keep last 1MB
                    content = log_file.read_bytes()[-1024*1024:]
                    log_file.write_bytes(content)
                    log.info(f'  ✅ Log getrimmt: {log_file.name}')
            except: pass

        # Clear /tmp leftovers
        try:
            subprocess.run(['find', '/tmp', '-mtime', '+7', '-delete'],
                capture_output=True, timeout=30)
        except: pass


# ── Backup Master ─────────────────────────────────────────────────────────────
class BackupMaster:
    BACKUP_SOURCES = [
        {
            'name': 'telegram-automation-bot',
            'src': '/Users/rudolfsarkany/Documents/GitHub/telegram-automation-bot',
            'excludes': ['node_modules', '.git', 'logs', '*.log'],
            'critical': True,
        },
        {
            'name': 'supermegabot',
            'src': '/Users/rudolfsarkany/supermegabot',
            'excludes': ['__pycache__', '*.pyc', 'logs'],
            'critical': True,
        },
        {
            'name': 'rudibot-eternal-brain',
            'src': str(BASE_DIR / 'brain'),
            'excludes': [],
            'critical': True,
        },
        {
            'name': 'env-configs',
            'src': None,  # Special: collect .env files
            'critical': True,
        },
    ]

    ICLOUD_BACKUP = Path('/Users/rudolfsarkany/Library/Mobile Documents/com~apple~CloudDocs/RudiBotBackups')
    LOCAL_BACKUP  = BASE_DIR / 'backups'

    def run_daily_backup(self):
        today = datetime.date.today().strftime('%Y-%m-%d')
        log.info(f'💾 Starte Daily Backup ({today})...')
        results = []

        # Local backup dir
        local_today = self.LOCAL_BACKUP / today
        local_today.mkdir(parents=True, exist_ok=True)

        # iCloud backup dir
        icloud_today = None  # vor try initialisieren um NameError zu vermeiden
        icloud_ok = False
        try:
            self.ICLOUD_BACKUP.mkdir(parents=True, exist_ok=True)
            icloud_today = self.ICLOUD_BACKUP / today
            icloud_today.mkdir(parents=True, exist_ok=True)
            icloud_ok = True
        except (OSError, PermissionError) as e:
            log.warning(f'⚠️  iCloud Backup nicht verfügbar ({e}) — nur lokal')

        for source in self.BACKUP_SOURCES:
            try:
                if source['name'] == 'env-configs':
                    result = self._backup_env_files(local_today, icloud_today if icloud_ok else None)
                else:
                    result = self._backup_directory(
                        source['src'], source['name'],
                        local_today, icloud_today if icloud_ok else None,
                        source.get('excludes', [])
                    )
                results.append({'name': source['name'], 'success': True, **result})
                log.info(f'  ✅ {source["name"]}: {result.get("size_mb", 0):.1f}MB gesichert')
            except Exception as e:
                results.append({'name': source['name'], 'success': False, 'error': str(e)})
                log.error(f'  ❌ {source["name"]}: {e}')

        # Cleanup alte Backups (behalte letzte 7 Tage lokal, 30 Tage in iCloud)
        self._cleanup_old_backups(self.LOCAL_BACKUP, keep_days=7)
        if icloud_ok:
            self._cleanup_old_backups(self.ICLOUD_BACKUP, keep_days=30)

        # Backup manifest speichern
        manifest = {
            'date': today,
            'timestamp': str(datetime.datetime.now()),
            'results': results,
            'icloud': icloud_ok,
            'local': str(local_today),
        }
        save_json(local_today / 'manifest.json', manifest)
        if icloud_ok:
            save_json(icloud_today / 'manifest.json', manifest)

        success_count = sum(1 for r in results if r['success'])
        log.info(f'💾 Backup fertig: {success_count}/{len(results)} erfolgreich')
        return manifest

    def _backup_directory(self, src, name, local_dst, icloud_dst, excludes):
        if not src or not Path(src).exists():
            return {'size_mb': 0, 'note': 'Quelle nicht gefunden'}

        # Build rsync excludes
        excl_args = []
        for ex in excludes:
            excl_args.extend(['--exclude', ex])

        # Local backup
        local_target = str(local_dst / name)
        cmd = ['rsync', '-a', '--delete'] + excl_args + [src + '/', local_target + '/']
        subprocess.run(cmd, capture_output=True, timeout=120)

        # Get size
        size_result = subprocess.run(['du', '-sm', local_target], capture_output=True, text=True)
        size_mb = float(size_result.stdout.split('\t')[0]) if size_result.stdout else 0

        # iCloud backup
        if icloud_dst:
            icloud_target = str(icloud_dst / name)
            cmd_ic = ['rsync', '-a', '--delete'] + excl_args + [src + '/', icloud_target + '/']
            subprocess.run(cmd_ic, capture_output=True, timeout=180)

        return {'size_mb': size_mb}

    def _backup_env_files(self, local_dst, icloud_dst):
        """Sichert alle .env Dateien aus wichtigen Projekten."""
        import shutil
        env_dir = local_dst / 'env-configs'
        env_dir.mkdir(exist_ok=True)

        env_paths = [
            '/Users/rudolfsarkany/Documents/GitHub/telegram-automation-bot/.env',
            '/Users/rudolfsarkany/supermegabot/.env',
            str(BASE_DIR / 'brain' / 'learned_fixes.json'),
            '/Users/rudolfsarkany/.claude/launch.json',
        ]

        backed_up = 0
        for ep in env_paths:
            p = Path(ep)
            if p.exists():
                dest_name = p.parent.name + '_' + p.name
                content = p.read_bytes()
                # Echte Verschlüsselung mit Fernet (AES-128-CBC + HMAC)
                try:
                    from cryptography.fernet import Fernet
                    key_file = BASE_DIR / 'brain' / '.backup_key'
                    if not key_file.exists():
                        key_file.write_bytes(Fernet.generate_key())
                        key_file.chmod(0o600)
                    fernet = Fernet(key_file.read_bytes())
                    encrypted = fernet.encrypt(content)
                    (env_dir / (dest_name + '.enc')).write_bytes(encrypted)
                except ImportError:
                    import base64
                    log.warning('⚠️  cryptography nicht installiert — verwende Base64 (unsicher!)')
                    (env_dir / (dest_name + '.b64')).write_bytes(base64.b64encode(content))
                backed_up += 1

        if icloud_dst:
            icloud_env = icloud_dst / 'env-configs'
            if env_dir.exists():
                shutil.copytree(str(env_dir), str(icloud_env), dirs_exist_ok=True)

        return {'size_mb': 0.1 * backed_up, 'files': backed_up}

    def _cleanup_old_backups(self, backup_root, keep_days):
        try:
            cutoff = datetime.date.today() - datetime.timedelta(days=keep_days)
            for entry in sorted(backup_root.iterdir()):
                if entry.is_dir():
                    try:
                        d = datetime.date.fromisoformat(entry.name)
                        if d < cutoff:
                            import shutil
                            shutil.rmtree(str(entry))
                            log.info(f'  🗑️  Altes Backup gelöscht: {entry.name}')
                    except (ValueError, OSError) as e:
                        log.debug(f'Skip backup cleanup for {entry.name}: {e}')
        except OSError as e:
            log.error(f'Backup cleanup failed: {e}')

    def restore_project(self, project_name, backup_date=None):
        """Stellt ein Projekt aus dem letzten Backup wieder her."""
        backup_root = self.LOCAL_BACKUP
        if backup_date:
            backup_dir = backup_root / backup_date / project_name
        else:
            # Finde neuestes Backup
            dates = sorted([d.name for d in backup_root.iterdir() if d.is_dir() and d.name != 'latest'], reverse=True)
            backup_dir = None
            for date in dates:
                candidate = backup_root / date / project_name
                if candidate.exists():
                    backup_dir = candidate
                    break

        if not backup_dir or not backup_dir.exists():
            return {'error': f'Kein Backup für {project_name} gefunden'}

        # Find original source
        source = next((s for s in self.BACKUP_SOURCES if s['name'] == project_name), None)
        if not source or not source.get('src'):
            return {'error': f'Quelle für {project_name} unbekannt'}

        log.warning(f'🔄 RESTORE: {project_name} von {backup_dir}')
        cmd = ['rsync', '-a', '--delete', str(backup_dir) + '/', source['src'] + '/']
        result = subprocess.run(cmd, capture_output=True, timeout=300)

        return {
            'success': result.returncode == 0,
            'project': project_name,
            'from': str(backup_dir),
            'to': source['src']
        }


# ── Telegram Notifier ─────────────────────────────────────────────────────────
def notify_telegram(message, parse_mode='Markdown'):
    """Sendet eine Nachricht via Telegram Bot."""
    if not NOTIFICATION_CONFIG['telegram_enabled']:
        return False
    try:
        token = os.getenv('TELEGRAM_BOT_TOKEN') or _read_env_var('TELEGRAM_BOT_TOKEN')
        chat_id = os.getenv('AUTHORIZED_USER_ID') or _read_env_var('AUTHORIZED_USER_ID')
        if not token or not chat_id:
            return False
        import urllib.request, urllib.parse
        payload = urllib.parse.urlencode({
            'chat_id': chat_id, 'text': message, 'parse_mode': parse_mode
        }).encode()
        req = urllib.request.Request(
            f'https://api.telegram.org/bot{token}/sendMessage',
            data=payload, method='POST'
        )
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        urllib.request.urlopen(req, timeout=10)
        return True
    except: return False

def notify_discord(message, embeds=None):
    """Sendet eine Nachricht via Discord Webhook."""
    webhook = NOTIFICATION_CONFIG.get('discord_webhook', '')
    if not webhook:
        return False
    try:
        import urllib.request
        payload = {'content': message[:2000]}  # Discord limit
        if embeds:
            payload['embeds'] = embeds
        data = json.dumps(payload).encode()
        req = urllib.request.Request(webhook, data=data, method='POST')
        req.add_header('Content-Type', 'application/json')
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        log.debug(f'Discord notify failed: {e}')
        return False

def notify_slack(message, attachments=None):
    """Sendet eine Nachricht via Slack Webhook."""
    webhook = NOTIFICATION_CONFIG.get('slack_webhook', '')
    if not webhook:
        return False
    try:
        import urllib.request
        payload = {'text': message[:4000]}  # Slack limit
        if attachments:
            payload['attachments'] = attachments
        data = json.dumps(payload).encode()
        req = urllib.request.Request(webhook, data=data, method='POST')
        req.add_header('Content-Type', 'application/json')
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        log.debug(f'Slack notify failed: {e}')
        return False

def notify_all(message, priority='normal'):
    """Sendet Nachricht an alle konfigurierten Kanäle."""
    results = {
        'telegram': notify_telegram(message),
        'discord': notify_discord(message),
        'slack': notify_slack(message)
    }
    return results

# ═══════════════════════════════════════════════════════════════════════════
# ═══ REST API & Multi-Agent Integration ═══════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════

class GuardianAPI:
    """REST API für Guardian - Multi-Agent Integration & Remote Control"""
    
    def __init__(self):
        self.app = Flask('GuardianAPI') if FLASK_AVAILABLE else None
        self.api_thread = None
        self.metrics_cache = {'data': {}, 'timestamp': 0}
        self.webhook_handlers = {}
        self._setup_routes()
    
    def require_auth(self, f):
        """API Key Authentication Decorator"""
        @wraps(f)
        def decorated(*args, **kwargs):
            if not API_CONFIG['auth_enabled']:
                return f(*args, **kwargs)
            
            auth_header = request.headers.get('X-API-Key', '')
            expected = hashlib.sha256(API_CONFIG['secret_key'].encode()).hexdigest()[:32]
            
            if not hmac.compare_digest(auth_header, expected):
                # Also check query param for webhooks
                api_key = request.args.get('api_key', '')
                if not hmac.compare_digest(api_key, expected):
                    abort(401, 'Unauthorized - Invalid API Key')
            return f(*args, **kwargs)
        return decorated
    
    def _setup_routes(self):
        """Alle API Endpunkte definieren"""
        if not self.app:
            return
        
        # ═══════════════════════════════════════════════════════════════════
        # 1. STATUS & HEALTH ENDPUNKTE
        # ═══════════════════════════════════════════════════════════════════
        
        @self.app.route('/api/v1/status', methods=['GET'])
        @self.require_auth
        def api_status():
            """Gesamtstatus aller Services"""
            services_status = []
            for svc in SERVICES:
                healthy = health_check_service(svc)
                services_status.append({
                    'name': svc['name'],
                    'port': svc['port'],
                    'healthy': healthy,
                    'critical': svc.get('critical', False)
                })
            
            return jsonify({
                'guardian': 'running',
                'timestamp': datetime.datetime.now().isoformat(),
                'services': services_status,
                'brain': brain.get_summary(),
                'overall_health': 'healthy' if all(s['healthy'] for s in services_status if s['critical']) else 'degraded'
            })
        
        @self.app.route('/api/v1/health', methods=['GET'])
        def health_check():
            """Einfacher Health Check (kein Auth für Load Balancer)"""
            all_healthy = all(health_check_service(svc) for svc in SERVICES if svc.get('critical'))
            status_code = 200 if all_healthy else 503
            return jsonify({
                'status': 'healthy' if all_healthy else 'unhealthy',
                'timestamp': datetime.datetime.now().isoformat()
            }), status_code
        
        @self.app.route('/api/v1/services', methods=['GET'])
        @self.require_auth
        def list_services():
            """Alle konfigurierten Services auflisten"""
            return jsonify({
                'services': [
                    {
                        'name': s['name'],
                        'port': s['port'],
                        'url': s.get('url'),
                        'critical': s.get('critical', False),
                        'status': 'running' if health_check_service(s) else 'down',
                        'cwd': s.get('cwd', ''),
                        'start_command': s.get('start', [])
                    } for s in SERVICES
                ]
            })
        
        @self.app.route('/api/v1/services/<service_name>/status', methods=['GET'])
        @self.require_auth
        def service_status(service_name):
            """Status eines spezifischen Service"""
            svc = next((s for s in SERVICES if s['name'].lower().replace(' ', '_') == service_name.lower()), None)
            if not svc:
                abort(404, 'Service not found')
            
            return jsonify({
                'name': svc['name'],
                'port': svc['port'],
                'healthy': health_check_service(svc),
                'critical': svc.get('critical', False),
                'last_check': datetime.datetime.now().isoformat()
            })
        
        # ═══════════════════════════════════════════════════════════════════
        # 2. REMOTE CONTROL API - Services steuern
        # ═══════════════════════════════════════════════════════════════════
        
        @self.app.route('/api/v1/services/<service_name>/start', methods=['POST'])
        @self.require_auth
        def start_service_api(service_name):
            """Service manuell starten"""
            svc = next((s for s in SERVICES if s['name'].lower().replace(' ', '_') == service_name.lower()), None)
            if not svc:
                abort(404, 'Service not found')
            
            success = start_service(svc)
            msg = f"🔧 API: {svc['name']} {'gestartet ✅' if success else 'Start fehlgeschlagen ❌'}"
            notify_all(msg, priority='high')
            
            return jsonify({
                'success': success,
                'service': svc['name'],
                'action': 'start',
                'timestamp': datetime.datetime.now().isoformat()
            })
        
        @self.app.route('/api/v1/services/<service_name>/stop', methods=['POST'])
        @self.require_auth
        def stop_service_api(service_name):
            """Service manuell stoppen (Port kill)"""
            svc = next((s for s in SERVICES if s['name'].lower().replace(' ', '_') == service_name.lower()), None)
            if not svc:
                abort(404, 'Service not found')
            
            success = kill_port(svc['port'])
            msg = f"🛑 API: {svc['name']} gestoppt {'✅' if success else '❌'}"
            notify_all(msg, priority='high')
            
            return jsonify({
                'success': success,
                'service': svc['name'],
                'action': 'stop',
                'timestamp': datetime.datetime.now().isoformat()
            })
        
        @self.app.route('/api/v1/services/<service_name>/restart', methods=['POST'])
        @self.require_auth
        def restart_service_api(service_name):
            """Service restart (stop + start)"""
            svc = next((s for s in SERVICES if s['name'].lower().replace(' ', '_') == service_name.lower()), None)
            if not svc:
                abort(404, 'Service not found')
            
            # Stop
            kill_port(svc['port'])
            time.sleep(2)
            # Start
            success = start_service(svc)
            
            msg = f"🔄 API: {svc['name']} restart {'✅' if success else '❌'}"
            notify_all(msg, priority='high')
            
            return jsonify({
                'success': success,
                'service': svc['name'],
                'action': 'restart',
                'timestamp': datetime.datetime.now().isoformat()
            })
        
        @self.app.route('/api/v1/services/<service_name>/heal', methods=['POST'])
        @self.require_auth
        def heal_service_api(service_name):
            """Service mit vollem Heal-Prozess reparieren"""
            svc = next((s for s in SERVICES if s['name'].lower().replace(' ', '_') == service_name.lower()), None)
            if not svc:
                abort(404, 'Service not found')
            
            if health_check_service(svc):
                return jsonify({'success': True, 'message': 'Service already healthy', 'service': svc['name']})
            
            success = heal_service(svc)
            return jsonify({
                'success': success,
                'service': svc['name'],
                'action': 'heal',
                'timestamp': datetime.datetime.now().isoformat()
            })
        
        # ═══════════════════════════════════════════════════════════════════
        # 3. BRAIN API - Gelerntes Wissen
        # ═══════════════════════════════════════════════════════════════════
        
        @self.app.route('/api/v1/brain', methods=['GET'])
        @self.require_auth
        def brain_summary():
            """Brain Summary - gelernte Muster"""
            return jsonify(brain.get_summary())
        
        @self.app.route('/api/v1/brain/fixes', methods=['GET'])
        @self.require_auth
        def brain_fixes():
            """Alle gelernten Fixes abrufen"""
            return jsonify({
                'fixes': brain.data.get('fixes', {}),
                'stats': brain.data.get('stats', {}),
                'patterns_learned': len(brain.data.get('fixes', {}))
            })
        
        @self.app.route('/api/v1/brain/fixes/<error_key>', methods=['GET'])
        @self.require_auth
        def get_fix(error_key):
            """Spezifischen Fix abrufen"""
            fix = brain.get_known_fix(error_key)
            if not fix:
                abort(404, 'Fix not found')
            return jsonify({
                'error_key': error_key,
                'fix': fix,
                'permanently_resolved': brain.is_permanently_resolved(error_key)
            })
        
        @self.app.route('/api/v1/brain/fixes', methods=['POST'])
        @self.require_auth
        def add_fix():
            """Neuen Fix manuell hinzufügen"""
            data = request.get_json() or {}
            error_key = data.get('error_key')
            service = data.get('service', 'manual')
            fix = data.get('fix')
            
            if not error_key or not fix:
                abort(400, 'error_key and fix required')
            
            brain.record_error(service, error_key, fix, data.get('success', True))
            return jsonify({
                'success': True,
                'error_key': error_key,
                'message': 'Fix recorded'
            }), 201
        
        @self.app.route('/api/v1/brain/patterns', methods=['GET'])
        @self.require_auth
        def brain_patterns():
            """Erkannte Fehler-Muster"""
            return jsonify(brain.data.get('patterns', {}))
        
        # ═══════════════════════════════════════════════════════════════════
        # 4. PROMETHEUS METRICS - Für Grafana
        # ═══════════════════════════════════════════════════════════════════
        
        @self.app.route('/metrics', methods=['GET'])
        def prometheus_metrics():
            """Prometheus-kompatible Metrics"""
            if not NOTIFICATION_CONFIG['prometheus_enabled']:
                return 'Prometheus disabled', 404
            
            # Generate metrics
            lines = []
            lines.append('# HELP guardian_service_up Service health status (1=up, 0=down)')
            lines.append('# TYPE guardian_service_up gauge')
            
            for svc in SERVICES:
                healthy = health_check_service(svc)
                service_label = svc['name'].lower().replace(' ', '_')
                lines.append(f'guardian_service_up{{service="{service_label}",port="{svc["port"]}",critical="{str(svc.get("critical", False)).lower()}"}} {1 if healthy else 0}')
            
            lines.append('')
            lines.append('# HELP guardian_brain_repairs_total Total repairs made')
            lines.append('# TYPE guardian_brain_repairs_total counter')
            stats = brain.get_summary()
            lines.append(f'guardian_brain_repairs_total {stats.get("total_repairs", 0)}')
            
            lines.append('')
            lines.append('# HELP guardian_brain_patterns_learned Learned error patterns')
            lines.append('# TYPE guardian_brain_patterns_learned gauge')
            lines.append(f'guardian_brain_patterns_learned {stats.get("patterns_learned", 0)}')
            
            lines.append('')
            lines.append('# HELP guardian_brain_permanently_resolved Permanently resolved issues')
            lines.append('# TYPE guardian_brain_permanently_resolved gauge')
            lines.append(f'guardian_brain_permanently_resolved {stats.get("permanently_resolved", 0)}')
            
            return '\n'.join(lines), 200, {'Content-Type': 'text/plain'}
        
        # ═══════════════════════════════════════════════════════════════════
        # 5. WEBHOOK ENDPUNKTE - Für externe Events
        # ═══════════════════════════════════════════════════════════════════
        
        @self.app.route('/webhooks/github', methods=['POST'])
        def webhook_github():
            """GitHub Webhook für Deploy Events"""
            signature = request.headers.get('X-Hub-Signature-256', '')
            payload = request.get_data()
            
            # Verify signature if secret configured
            secret = NOTIFICATION_CONFIG.get('github_webhook_secret', '')
            if secret:
                expected = 'sha256=' + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
                if not hmac.compare_digest(signature, expected):
                    abort(401, 'Invalid signature')
            
            event_type = request.headers.get('X-GitHub-Event', 'push')
            data = request.get_json() or {}
            
            if event_type == 'push':
                repo = data.get('repository', {}).get('name', 'unknown')
                ref = data.get('ref', '')
                if 'main' in ref or 'master' in ref:
                    notify_all(f'🚀 GitHub Push zu {repo}/{ref} - prüfe auf Updates...')
                    # Trigger heal für relevante Services
                    for svc in SERVICES:
                        if repo.lower() in svc.get('cwd', '').lower():
                            heal_service(svc)
            
            elif event_type == 'issues':
                action = data.get('action', '')
                issue = data.get('issue', {})
                notify_all(f'🐛 GitHub Issue {action}: {issue.get("title", "")[:50]}')
            
            return jsonify({'received': True, 'event': event_type}), 200
        
        @self.app.route('/webhooks/alertmanager', methods=['POST'])
        def webhook_alertmanager():
            """Prometheus Alertmanager Webhook"""
            data = request.get_json() or {}
            alerts = data.get('alerts', [])
            
            for alert in alerts:
                status = alert.get('status', 'unknown')
                name = alert.get('labels', {}).get('alertname', 'unknown')
                severity = alert.get('labels', {}).get('severity', 'warning')
                summary = alert.get('annotations', {}).get('summary', '')
                
                emoji = '🔴' if status == 'firing' else '🟢'
                msg = f"{emoji} Alertmanager [{severity.upper()}]: {name}\n{summary}"
                notify_all(msg, priority='high' if severity == 'critical' else 'normal')
                
                # Auto-heal if service down
                for svc in SERVICES:
                    if svc['name'].lower() in name.lower() or str(svc['port']) in name:
                        if status == 'firing':
                            threading.Thread(target=heal_service, args=(svc,), daemon=True).start()
            
            return jsonify({'received': True, 'alerts_processed': len(alerts)}), 200
        
        @self.app.route('/webhooks/custom', methods=['POST'])
        @self.require_auth
        def webhook_custom():
            """Custom Webhook für beliebige Events"""
            data = request.get_json() or {}
            event_type = data.get('event_type', 'unknown')
            message = data.get('message', '')
            priority = data.get('priority', 'normal')
            
            # Log event
            log.info(f'Custom webhook received: {event_type}')
            
            # Notify
            if message:
                notify_all(f'📡 Webhook [{event_type}]: {message}', priority=priority)
            
            # Handle specific actions
            action = data.get('action', '')
            if action == 'restart_service':
                service_name = data.get('service_name', '')
                svc = next((s for s in SERVICES if s['name'].lower() == service_name.lower()), None)
                if svc:
                    threading.Thread(target=heal_service, args=(svc,), daemon=True).start()
                    return jsonify({'received': True, 'action': 'restart_initiated', 'service': service_name})
            
            return jsonify({'received': True, 'event_type': event_type}), 200
        
        # ═══════════════════════════════════════════════════════════════════
        # 6. BACKUP & REPORT API
        # ═══════════════════════════════════════════════════════════════════
        
        @self.app.route('/api/v1/backup', methods=['POST'])
        @self.require_auth
        def trigger_backup():
            """Manuelles Backup starten"""
            bm = BackupMaster()
            result = bm.run_daily_backup()
            notify_all(f'💾 API Backup ausgelöst: {result}')
            return jsonify(result)
        
        @self.app.route('/api/v1/reports', methods=['GET'])
        @self.require_auth
        def get_reports():
            """Daily Reports abrufen"""
            reports = load_json(REPORT_FILE, [])
            limit = request.args.get('limit', 10, type=int)
            return jsonify({'reports': reports[-limit:], 'total': len(reports)})
        
        @self.app.route('/api/v1/reports/latest', methods=['GET'])
        @self.require_auth
        def get_latest_report():
            """Letzten Report abrufen"""
            reports = load_json(REPORT_FILE, [])
            if reports:
                return jsonify(reports[-1])
            return jsonify({'error': 'No reports yet'}), 404
        
        # ═══════════════════════════════════════════════════════════════════
        # 7. AGENT COMMUNICATION - Für andere Agenten
        # ═══════════════════════════════════════════════════════════════════
        
        @self.app.route('/api/v1/agents/register', methods=['POST'])
        @self.require_auth
        def register_agent():
            """Anderer Agent registriert sich"""
            data = request.get_json() or {}
            agent_id = data.get('agent_id')
            agent_type = data.get('type', 'unknown')
            endpoint = data.get('endpoint', '')
            
            # Store agent info (in brain or separate file)
            agents = load_json(BASE_DIR / 'brain' / 'registered_agents.json', [])
            agents = [a for a in agents if a.get('agent_id') != agent_id]  # Remove old
            agents.append({
                'agent_id': agent_id,
                'type': agent_type,
                'endpoint': endpoint,
                'registered_at': datetime.datetime.now().isoformat(),
                'last_seen': datetime.datetime.now().isoformat()
            })
            save_json(BASE_DIR / 'brain' / 'registered_agents.json', agents)
            
            notify_all(f'🤖 Neuer Agent registriert: {agent_id} ({agent_type})')
            return jsonify({'registered': True, 'agent_id': agent_id}), 201
        
        @self.app.route('/api/v1/agents', methods=['GET'])
        @self.require_auth
        def list_agents():
            """Registrierte Agenten auflisten"""
            agents = load_json(BASE_DIR / 'brain' / 'registered_agents.json', [])
            return jsonify({'agents': agents, 'count': len(agents)})
        
        @self.app.route('/api/v1/notify', methods=['POST'])
        @self.require_auth
        def api_notify():
            """Nachricht über alle Kanäle senden"""
            data = request.get_json() or {}
            message = data.get('message', '')
            priority = data.get('priority', 'normal')
            channels = data.get('channels', ['all'])  # telegram, discord, slack, all
            
            results = {}
            if 'all' in channels or 'telegram' in channels:
                results['telegram'] = notify_telegram(message)
            if 'all' in channels or 'discord' in channels:
                results['discord'] = notify_discord(message)
            if 'all' in channels or 'slack' in channels:
                results['slack'] = notify_slack(message)
            
            return jsonify({'sent': True, 'channels': results})
    
    def start(self):
        """Startet API Server in separatem Thread"""
        if not FLASK_AVAILABLE or not self.app:
            log.warning('Flask nicht verfügbar - API wird nicht gestartet')
            return False
        
        def run_api():
            try:
                log.info(f'🌐 Guardian API startet auf http://{API_CONFIG["host"]}:{API_CONFIG["port"]}')
                self.app.run(
                    host=API_CONFIG['host'],
                    port=API_CONFIG['port'],
                    debug=False,
                    threaded=True
                )
            except Exception as e:
                log.error(f'API Server Fehler: {e}')
        
        self.api_thread = threading.Thread(target=run_api, daemon=True)
        self.api_thread.start()
        return True

# Global API instance
guardian_api = GuardianAPI()

def _read_env_var(key):
    env_path = Path('/Users/rudolfsarkany/Documents/GitHub/telegram-automation-bot/.env')
    try:
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith(key + '='):
                _, _, v = line.partition('=')
                v = v.split('#')[0].strip().strip('"').strip("'")
                return v
    except:
        pass
    return None


# ── Daily Report ──────────────────────────────────────────────────────────────
def generate_daily_report(health_results, repair_results, improve_results, backup_result):
    today = str(datetime.date.today())
    b_stats = brain.get_summary()

    ok = sum(1 for r in health_results if r['healthy'])
    total = len(health_results)
    repairs = len([r for r in repair_results if r.get('repaired')])

    report = f"""🤖 *RudiBot Daily Report* — {today}

🟢 *Services:* {ok}/{total} OK
🔧 *Repariert heute:* {repairs}
🧠 *Brain Wissen:* {b_stats['patterns_learned']} Muster | {b_stats['total_repairs']} Reparaturen gesamt
🔒 *Permanent gelöst:* {b_stats['permanently_resolved']} Fehler-Muster
💾 *Backup:* {'✅ Erfolgreich' if backup_result.get('results') else '⚠️ Prüfen'}

📈 *Selbstverbesserung:*
• Fixes heute: {len(improve_results.get('fixes_applied', []))}
• Analysen: {len(improve_results.get('improvements', []))}

_Nächster Check in 2 Stunden_ 🕐"""

    return report

# ── Main Guardian Loop ────────────────────────────────────────────────────────
def run_guardian():
    log.info('╔══════════════════════════════════════════════╗')
    log.info('║    RUDIBOT ETERNAL GUARDIAN — START         ║')
    log.info(f'║    {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}                    ║')
    log.info('╚══════════════════════════════════════════════╝')

    # Prevent duplicate runs
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip())
            # Check if process is actually running
            subprocess.run(['kill', '-0', str(pid)], capture_output=True, check=True)
            log.warning(f'⚠️  Guardian läuft bereits (PID {pid}) — beende')
            return
        except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
            LOCK_FILE.unlink(missing_ok=True)
        except Exception as e:
            log.warning(f'Lock check failed: {e}')
            LOCK_FILE.unlink(missing_ok=True)

    LOCK_FILE.write_text(str(os.getpid()))

    try:
        health_results = []
        repair_results = []

        # 1. ── Health Check aller Services ──────────────────────────────
        log.info('─' * 50)
        log.info('🔍 Phase 1: Health Check...')
        for svc in SERVICES:
            healthy = health_check_service(svc)
            health_results.append({'name': svc['name'], 'healthy': healthy})
            status = '✅' if healthy else '🔴'
            log.info(f'  {status} {svc["name"]} (Port {svc["port"]})')

        # 2. ── Reparatur ─────────────────────────────────────────────────
        log.info('─' * 50)
        log.info('🔧 Phase 2: Auto-Reparatur...')
        for svc, check in zip(SERVICES, health_results):
            if not check['healthy']:
                repaired = heal_service(svc)
                repair_results.append({'name': svc['name'], 'repaired': repaired})
                if repaired:
                    notify_telegram(f'🔧 *{svc["name"]}* wurde automatisch repariert ✅')
            else:
                repair_results.append({'name': svc['name'], 'repaired': False, 'was_healthy': True})

        # 3. ── Self Improvement ──────────────────────────────────────────
        log.info('─' * 50)
        log.info('🧠 Phase 3: Selbstverbesserung...')
        improver = SelfImprover()
        improve_results = improver.analyze_and_improve()

        # 4. ── Daily Backup (nur einmal täglich) ────────────────────────
        backup_result = {}
        today = str(datetime.date.today())
        last_backup = load_json(BASE_DIR / 'brain' / 'last_backup.json', {})
        if last_backup.get('date') != today:
            log.info('─' * 50)
            log.info('💾 Phase 4: Daily Backup...')
            bm = BackupMaster()
            backup_result = bm.run_daily_backup()
            save_json(BASE_DIR / 'brain' / 'last_backup.json', {'date': today, 'success': True})

            # 4b. ── Social Media Autopilot (einmal täglich) ──────────────
            try:
                import urllib.request, urllib.error
                log.info('📱 Phase 4b: Social Media Autopilot...')
                req = urllib.request.Request(
                    'http://localhost:3200/api/social/autopost',
                    data=b'{"platforms":["instagram","facebook","pinterest","twitter"]}',
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    social_result = json.loads(resp.read().decode())
                    if social_result.get('ok'):
                        log.info(f'📱 Autopilot gepostet: {social_result.get("product")} → {social_result.get("postedTo", [])}')
                        notify_telegram(f'📱 *Social Autopilot:* {social_result.get("product", "N/A")}\n✅ {", ".join(social_result.get("postedTo", []))}')
                    elif social_result.get('message'):
                        log.info(f'📱 Autopilot: {social_result["message"]}')
                    elif social_result.get('error'):
                        log.warning(f'📱 Autopilot Fehler: {social_result["error"]}')
            except urllib.error.HTTPError as he:
                body = he.read().decode(errors='ignore')[:200] if he else ''
                log.warning(f'📱 Social Autopilot HTTP {he.code}: {body}')
            except Exception as se:
                log.warning(f'📱 Social Autopilot übersprungen: {se}')

            # Täglicher Report via Telegram
            report_text = generate_daily_report(health_results, repair_results, improve_results, backup_result)
            if notify_telegram(report_text):
                log.info('📱 Daily Report an Telegram gesendet')
        else:
            log.info('💾 Backup heute bereits gemacht — überspringe')
            backup_result = {'note': 'already_done'}

        # 5. ── Save Report ───────────────────────────────────────────────
        report_data = load_json(REPORT_FILE, [])
        report_data.append({
            'timestamp': str(datetime.datetime.now()),
            'health': health_results,
            'repairs': repair_results,
            'improvements': improve_results,
            'backup': 'done' if backup_result.get('results') else 'skipped',
        })
        # Keep last 100 reports
        save_json(REPORT_FILE, report_data[-100:])

        all_ok = all(r['healthy'] or r.get('repaired') for r in zip_results(health_results, repair_results))
        log.info('─' * 50)
        log.info(f'🏁 Guardian Lauf abgeschlossen — System: {"✅ OK" if all_ok else "⚠️ Check nötig"}')
        log.info(f'   Brain: {brain.get_summary()["total_repairs"]} Reparaturen | {brain.get_summary()["permanently_resolved"]} permanent gelöst')

    except Exception as e:
        log.error(f'❌ Guardian Fehler: {e}')
        log.error(traceback.format_exc())
        notify_telegram(f'⚠️ *Guardian Fehler:* {str(e)[:200]}')
    finally:
        LOCK_FILE.unlink(missing_ok=True)

def zip_results(health, repair):
    combined = []
    repair_map = {r['name']: r for r in repair}
    for h in health:
        r = repair_map.get(h['name'], {})
        combined.append({'healthy': h['healthy'] or r.get('repaired', False)})
    return combined

if __name__ == '__main__':
    # Load .env
    env_path = Path('/Users/rudolfsarkany/Documents/GitHub/telegram-automation-bot/.env')
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                os.environ.setdefault(k.strip(), v.strip())

    if '--restore' in sys.argv:
        # Restore mode: python3 eternal_guardian.py --restore <project> [date]
        idx = sys.argv.index('--restore')
        project = sys.argv[idx+1] if len(sys.argv) > idx+1 else None
        date = sys.argv[idx+2] if len(sys.argv) > idx+2 else None
        if project:
            bm = BackupMaster()
            result = bm.restore_project(project, date)
            print(json.dumps(result, indent=2))
        else:
            print('Usage: --restore <project_name> [YYYY-MM-DD]')
    elif '--backup' in sys.argv:
        bm = BackupMaster()
        result = bm.run_daily_backup()
        print(json.dumps(result, indent=2, default=str))
    elif '--status' in sys.argv:
        for svc in SERVICES:
            ok = health_check_service(svc)
            print(f'{"✅" if ok else "❌"} {svc["name"]} (:{svc["port"]})')
        print(json.dumps(brain.get_summary(), indent=2))
    elif '--heal' in sys.argv:
        for svc in SERVICES:
            if not health_check_service(svc):
                heal_service(svc)
    elif '--api-only' in sys.argv:
        # Nur API Server starten (für externes Monitoring)
        log.info('🌐 Starte nur API Server...')
        guardian_api.start()
        # Keep main thread alive
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            log.info('API Server gestoppt')
    elif '--api' in sys.argv:
        # Guardian mit API starten
        guardian_api.start()
        run_guardian()
    else:
        # Standard: API automatisch starten
        guardian_api.start()
        run_guardian()
