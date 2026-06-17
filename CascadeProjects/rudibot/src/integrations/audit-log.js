/**
 * Audit Log Integration — Centralized logging for all KIVO operations
 * Logs approvals, security events, user actions, and system changes
 */

const fs = require('fs');
const path = require('path');

const AUDIT_DIR = path.join(process.cwd(), 'logs');
const AUDIT_FILE = path.join(AUDIT_DIR, 'kivo-audit.log');
const SECURITY_FILE = path.join(AUDIT_DIR, 'security-events.log');
const SYSTEM_FILE = path.join(AUDIT_DIR, 'system-events.log');

function ensureDir(dir) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

class AuditLog {
  constructor(options = {}) {
    this.config = {
      maxEntries: options.maxEntries || 10000,
      flushInterval: options.flushInterval || 5000,
      logToConsole: options.logToConsole !== false,
      ...options
    };

    this.buffer = [];
    this.securityBuffer = [];
    this.systemBuffer = [];
    this.totalEntries = 0;
    
    // Periodic flush
    setInterval(() => this.flush(), this.config.flushInterval);
  }

  // ── Core Logging ───────────────────────────────────────────
  log(eventType, data, severity = 'info') {
    const entry = {
      timestamp: new Date().toISOString(),
      type: eventType,
      severity,
      ...data
    };

    this.buffer.push(entry);
    this.totalEntries++;

    if (this.config.logToConsole) {
      console.log(`[AUDIT] ${eventType}:`, JSON.stringify(data, null, 2));
    }

    // Auto-flush if buffer is large
    if (this.buffer.length > 100) {
      this.flush();
    }

    return entry;
  }

  logSecurity(eventType, data) {
    const entry = {
      timestamp: new Date().toISOString(),
      type: eventType,
      category: 'security',
      ...data
    };

    this.securityBuffer.push(entry);
    
    if (this.config.logToConsole) {
      console.log(`[SECURITY] ${eventType}:`, JSON.stringify(data, null, 2));
    }

    return entry;
  }

  logSystem(eventType, data) {
    const entry = {
      timestamp: new Date().toISOString(),
      type: eventType,
      category: 'system',
      ...data
    };

    this.systemBuffer.push(entry);
    
    if (this.config.logToConsole) {
      console.log(`[SYSTEM] ${eventType}:`, JSON.stringify(data, null, 2));
    }

    return entry;
  }

  // ── Event-Specific Loggers ─────────────────────────────────
  logApproval(userId, action, approved, details = {}) {
    return this.log('approval', {
      userId,
      action,
      approved,
      ...details
    }, approved ? 'info' : 'warning');
  }

  logAction(userId, action, result, details = {}) {
    return this.log('action', {
      userId,
      action,
      result,
      ...details
    }, result === 'success' ? 'info' : 'error');
  }

  logIntent(userId, text, intent, confidence) {
    return this.log('intent', {
      userId,
      text,
      intent,
      confidence
    });
  }

  logVoice(userId, audioDuration, transcript, confidence) {
    return this.log('voice', {
      userId,
      audioDuration,
      transcript,
      confidence
    });
  }

  logHomeAction(userId, device, action, result) {
    return this.log('home_action', {
      userId,
      device,
      action,
      result
    });
  }

  logFinanceAction(userId, action, scope, result) {
    return this.log('finance_action', {
      userId,
      action,
      scope,
      result
    });
  }

  logSecurityEvent(eventType, details) {
    return this.logSecurity(eventType, details);
  }

  logSystemEvent(eventType, details) {
    return this.logSystem(eventType, details);
  }

  logError(source, error, context = {}) {
    return this.log('error', {
      source,
      error: error.message || error,
      stack: error.stack,
      ...context
    }, 'error');
  }

  logWorkflow(userId, workflowId, status, details = {}) {
    return this.log('workflow', {
      userId,
      workflowId,
      status,
      ...details
    });
  }

  // ── File Persistence ───────────────────────────────────────
  flush() {
    if (this.buffer.length === 0 && this.securityBuffer.length === 0 && this.systemBuffer.length === 0) {
      return;
    }

    ensureDir(AUDIT_DIR);

    // Flush main audit log
    if (this.buffer.length > 0) {
      const lines = this.buffer.map(e => JSON.stringify(e)).join('\n') + '\n';
      fs.appendFileSync(AUDIT_FILE, lines);
      this.buffer = [];
    }

    // Flush security log
    if (this.securityBuffer.length > 0) {
      const lines = this.securityBuffer.map(e => JSON.stringify(e)).join('\n') + '\n';
      fs.appendFileSync(SECURITY_FILE, lines);
      this.securityBuffer = [];
    }

    // Flush system log
    if (this.systemBuffer.length > 0) {
      const lines = this.systemBuffer.map(e => JSON.stringify(e)).join('\n') + '\n';
      fs.appendFileSync(SYSTEM_FILE, lines);
      this.systemBuffer = [];
    }
  }

  // ── Query & Retrieval ─────────────────────────────────────
  async query(options = {}) {
    const {
      type = null,
      userId = null,
      startDate = null,
      endDate = null,
      severity = null,
      limit = 100
    } = options;

    const results = [];
    const files = [AUDIT_FILE, SECURITY_FILE, SYSTEM_FILE];

    for (const file of files) {
      if (!fs.existsSync(file)) continue;

      const lines = fs.readFileSync(file, 'utf8').split('\n').filter(Boolean);
      
      for (let i = lines.length - 1; i >= 0; i--) {
        try {
          const entry = JSON.parse(lines[i]);

          if (type && entry.type !== type) continue;
          if (userId && entry.userId !== userId) continue;
          if (severity && entry.severity !== severity) continue;
          if (startDate && new Date(entry.timestamp) < new Date(startDate)) continue;
          if (endDate && new Date(entry.timestamp) > new Date(endDate)) continue;

          results.push(entry);

          if (results.length >= limit) break;
        } catch (e) {
          // Skip corrupt lines
          continue;
        }
      }

      if (results.length >= limit) break;
    }

    return results;
  }

  async getRecent(userId = null, limit = 50) {
    return this.query({ userId, limit });
  }

  async getSecurityEvents(limit = 50) {
    return this.query({ type: null, limit }); // Will scan all files for security entries
  }

  async getStats(period = '24h') {
    const startDate = new Date(Date.now() - this.parsePeriod(period));
    
    const entries = await this.query({ startDate, limit: 10000 });
    
    const stats = {
      total: entries.length,
      byType: {},
      bySeverity: {},
      byUser: {},
      period
    };

    for (const entry of entries) {
      stats.byType[entry.type] = (stats.byType[entry.type] || 0) + 1;
      stats.bySeverity[entry.severity] = (stats.bySeverity[entry.severity] || 0) + 1;
      if (entry.userId) {
        stats.byUser[entry.userId] = (stats.byUser[entry.userId] || 0) + 1;
      }
    }

    return stats;
  }

  parsePeriod(period) {
    const match = period.match(/^(\d+)([hdwmy])$/);
    if (!match) return 24 * 60 * 60 * 1000; // Default 24h

    const value = parseInt(match[1]);
    const unit = match[2];

    const multipliers = {
      h: 60 * 60 * 1000,
      d: 24 * 60 * 60 * 1000,
      w: 7 * 24 * 60 * 60 * 1000,
      m: 30 * 24 * 60 * 60 * 1000,
      y: 365 * 24 * 60 * 60 * 1000
    };

    return value * multipliers[unit];
  }

  // ── Cleanup ───────────────────────────────────────────────
  cleanup(maxAge = 30 * 24 * 60 * 60 * 1000) { // 30 days
    const files = [AUDIT_FILE, SECURITY_FILE, SYSTEM_FILE];
    let removed = 0;

    for (const file of files) {
      if (!fs.existsSync(file)) continue;

      const lines = fs.readFileSync(file, 'utf8').split('\n').filter(Boolean);
      const cutoff = Date.now() - maxAge;
      
      const filtered = lines.filter(line => {
        try {
          const entry = JSON.parse(line);
          return new Date(entry.timestamp).getTime() > cutoff;
        } catch (e) {
          return false;
        }
      });

      removed += lines.length - filtered.length;
      fs.writeFileSync(file, filtered.join('\n') + (filtered.length > 0 ? '\n' : ''));
    }

    return removed;
  }

  // ── Status ─────────────────────────────────────────────────
  getStatus() {
    return {
      totalEntries: this.totalEntries,
      buffered: this.buffer.length,
      securityBuffered: this.securityBuffer.length,
      systemBuffered: this.systemBuffer.length,
      logDir: AUDIT_DIR,
      maxEntries: this.config.maxEntries
    };
  }

  // ── Shutdown ──────────────────────────────────────────────
  shutdown() {
    this.flush();
  }
}

module.exports = { AuditLog };
