import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, '../../');

export class UnifiedLogger {
  constructor(options = {}) {
    this.name = options.name || 'bot';
    this.logDir = options.logDir || path.join(PROJECT_ROOT, 'logs');
    this.logFile = path.join(this.logDir, `${this.name}.log`);
    this.maxLogSize = options.maxLogSize || 5 * 1024 * 1024;
    this.maxBackups = options.maxBackups || 5;
    this.consoleOutput = options.consoleOutput !== false;
    this.structured = options.structured !== false;

    if (!fs.existsSync(this.logDir)) {
      fs.mkdirSync(this.logDir, { recursive: true });
    }
  }

  checkRotation() {
    try {
      if (fs.existsSync(this.logFile)) {
        const stats = fs.statSync(this.logFile);
        if (stats.size > this.maxLogSize) {
          this.rotate();
        }
      }
    } catch (err) {
      console.error(`[${this.name}] Log rotation error:`, err.message);
    }
  }

  rotate() {
    try {
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      const backup = `${this.logFile}.${timestamp}.backup`;
      fs.renameSync(this.logFile, backup);
      this.cleanupOldBackups();
    } catch (err) {
      console.error(`[${this.name}] Rotate error:`, err.message);
    }
  }

  cleanupOldBackups() {
    try {
      const files = fs.readdirSync(this.logDir)
        .filter(f => f.startsWith(`${this.name}.log.`) && f.endsWith('.backup'))
        .map(f => ({ name: f, path: path.join(this.logDir, f), time: fs.statSync(path.join(this.logDir, f)).mtime.getTime() }))
        .sort((a, b) => b.time - a.time);

      if (files.length > this.maxBackups) {
        files.slice(this.maxBackups).forEach(f => {
          try { fs.unlinkSync(f.path); } catch {}
        });
      }
    } catch {}
  }

  format(level, message, meta = {}) {
    const timestamp = new Date().toISOString();
    if (this.structured) {
      return JSON.stringify({ timestamp, level: level.toUpperCase(), bot: this.name, message, ...meta }) + '\n';
    }
    const metaStr = Object.keys(meta).length ? ' | ' + JSON.stringify(meta) : '';
    return `[${timestamp}] [${level.toUpperCase()}] [${this.name}] ${message}${metaStr}\n`;
  }

  log(level, message, meta = {}) {
    this.checkRotation();
    const line = this.format(level, message, meta);
    try {
      fs.appendFileSync(this.logFile, line);
    } catch {}
    if (this.consoleOutput) {
      const colors = { debug: '\x1b[36m', info: '\x1b[32m', warn: '\x1b[33m', error: '\x1b[31m', reset: '\x1b[0m' };
      const c = colors[level] || '';
      console.log(`${c}[${this.name}] ${message}${colors.reset}`);
    }
  }

  debug(msg, meta) { this.log('debug', msg, meta); }
  info(msg, meta) { this.log('info', msg, meta); }
  warn(msg, meta) { this.log('warn', msg, meta); }
  error(msg, meta) { this.log('error', msg, meta); }
}
