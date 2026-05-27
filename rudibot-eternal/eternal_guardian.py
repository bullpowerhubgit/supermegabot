#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║          RUDIBOT ETERNAL GUARDIAN v1.0                          ║
║  Selbstheilend · Selbstverbessernd · Niemals kaputt             ║
║  Läuft alle 2h · Repariert bis fehlerfrei · Lernt jeden Tag    ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os, sys, json, time, logging, subprocess, datetime, signal, traceback
from pathlib import Path

BASE_DIR    = Path(__file__).parent
BRAIN_FILE  = BASE_DIR / 'brain' / 'learned_fixes.json'
REPORT_FILE = BASE_DIR / 'brain' / 'daily_reports.json'
IMPROVE_LOG = BASE_DIR / 'brain' / 'improvement_log.json'
LOG_FILE    = BASE_DIR / 'logs' / 'eternal.log'
LOCK_FILE   = BASE_DIR / '.running.lock'

# ── Logging ──────────────────────────────────────────────────────────────────
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

# ── Service Registry ─────────────────────────────────────────────────────────
SERVICES = [
    {
        'name':     'RudiBot Main',
        'port':     3200,
        'url':      'http://localhost:3200/health',
        'cwd':      '/Users/rudolfsarkany/Documents/GitHub/telegram-automation-bot',
        'start':    ['node', 'server.js'],
        'check':    'http',
        'critical': True,
    },
    {
        'name':     'Ollama LLM',
        'port':     11434,
        'url':      'http://localhost:11434/api/tags',
        'cwd':      '/Users/rudolfsarkany',
        'start':    ['ollama', 'serve'],
        'check':    'http',
        'critical': True,
    },
    {
        'name':     'Redis',
        'port':     6379,
        'url':      None,
        'cwd':      '/Users/rudolfsarkany',
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
            if e['count'] >= 3 and e['success_rate'] == 100:
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
        s = socket.socket()
        s.settimeout(2)
        s.connect(('127.0.0.1', port))
        s.close()
        return True
    except: return False

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
        cwd = svc.get('cwd', '/Users/rudolfsarkany')
        if not Path(cwd).exists():
            log.error(f'  ❌ CWD nicht gefunden: {cwd}')
            return False
        env = os.environ.copy()
        env['PATH'] = '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:' + env.get('PATH', '')

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
    """Heilt einen fehlerhaften Dienst — versucht es bis es klappt."""
    name = svc['name']
    error_key = f'{name}_down'

    if attempt > 5:
        log.error(f'❌ {name}: Konnte nach 5 Versuchen nicht reparieren')
        brain.record_error(name, error_key, 'manual_restart_needed', False)
        return False

    log.warning(f'🔴 {name} ist down (Versuch {attempt}/5)')

    # Strategie je Versuch
    if attempt >= 2:
        log.info(f'  🔫 Beende Prozess auf Port {svc["port"]}')
        kill_port(svc['port'])
        time.sleep(2)

    if attempt >= 3:
        # Clear npm/node cache wenn Node-Dienst
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
        # Reinstall dependencies
        cwd = svc.get('cwd', '')
        if cwd and Path(cwd).joinpath('package.json').exists():
            log.info(f'  📦 npm install in {cwd}')
            try:
                subprocess.run(['npm', 'install', '--omit=dev'],
                    cwd=cwd, capture_output=True, timeout=120, env={
                        **os.environ,
                        'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:' + os.environ.get('PATH','')
                    })
            except: pass

    success = start_service(svc)
    brain.record_error(name, error_key, f'restart_attempt_{attempt}', success)

    if not success:
        time.sleep(5 * attempt)
        return heal_service(svc, attempt + 1)

    log.info(f'✅ {name} erfolgreich repariert nach {attempt} Versuch(en)')
    return True

# ── Self Improver: Verbessert sich täglich ────────────────────────────────────
class SelfImprover:
    def __init__(self):
        self.log_data = load_json(IMPROVE_LOG, {'improvements': [], 'score': 0})

    def analyze_and_improve(self):
        improvements = []
        today = str(datetime.date.today())

        # 1. Server-Logs auf Fehler analysieren
        bot_log = Path('/Users/rudolfsarkany/Library/Mobile Documents/com~apple~CloudDocs/Documents/GitHub/telegram-automation-bot/logs')
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
                                env={**os.environ, 'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:'+os.environ.get('PATH','')}
                            )
                            if result.returncode == 0:
                                fixes_applied.append(f'npm install in {cwd}')
                                brain.record_error('auto_improve', error, 'npm_install', True)
                        except: pass

            elif error == 'SyntaxError':
                fixes_applied.append('SyntaxError erkannt — manuelle Prüfung empfohlen')

        # 3. Disk Space Check + Cleanup
        try:
            result = subprocess.run(['df', '-h', '/'], capture_output=True, text=True)
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

        # 4. Memory pressure check
        try:
            result = subprocess.run(
                ["vm_stat"], capture_output=True, text=True
            )
            if 'page' in result.stdout.lower():
                # Check swap usage
                swap = subprocess.run(['sysctl', 'vm.swapusage'], capture_output=True, text=True)
                if 'used = ' in swap.stdout:
                    used_str = swap.stdout.split('used = ')[1].split('M')[0]
                    try:
                        used_mb = float(used_str.strip())
                        if used_mb > 2000:
                            improvements.append(f'⚠️ Hoher Swap: {used_mb:.0f}MB — Neustart empfohlen')
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
                            env={**os.environ, 'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:'+os.environ.get('PATH','')}
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
        try:
            self.ICLOUD_BACKUP.mkdir(parents=True, exist_ok=True)
            icloud_today = self.ICLOUD_BACKUP / today
            icloud_today.mkdir(parents=True, exist_ok=True)
            icloud_ok = True
        except (OSError, PermissionError) as e:
            icloud_ok = False
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
                # Encrypt sensitive files (base64 obfuscation)
                content = p.read_bytes()
                import base64
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

def _read_env_var(key):
    env_path = Path('/Users/rudolfsarkany/Documents/GitHub/telegram-automation-bot/.env')
    try:
        for line in env_path.read_text().splitlines():
            if line.startswith(key + '='):
                return line.split('=', 1)[1].strip()
    except: pass
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
    else:
        run_guardian()
