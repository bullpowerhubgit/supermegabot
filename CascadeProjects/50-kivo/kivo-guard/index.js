/**
 * KIVO GUARD — Roles, Approvals, Sensitive Actions, Audit Logs
 * Safety layer ensuring no risky blind actions are executed
 */

const fs = require('fs');
const path = require('path');

const AUDIT_DIR = path.join(process.cwd(), 'logs');
const AUDIT_FILE = path.join(AUDIT_DIR, 'kivo-guard-audit.log');

function ensureDir(dir) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

const ROLES = {
  guest: { can: ['home.status', 'home.health'], maxApprovalLevel: 0 },
  user: { can: ['home.*', 'finance.overview', 'finance.subscriptions', 'finance.spend', 'finance.tax', 'system.status'], maxApprovalLevel: 1 },
  admin: { can: ['*'], maxApprovalLevel: 3 },
};

const APPROVAL_LEVELS = {
  0: 'none',
  1: 'notification', // Just notify, no block
  2: 'confirm_once', // Confirm once per session
  3: 'confirm_always', // Always confirm
};

const SENSITIVE_ACTIONS = [
  { pattern: 'finance.kill_subscription', level: 2, reason: 'Subscription cancellation is irreversible' },
  { pattern: 'finance.elster', level: 2, reason: 'ELSTER export involves tax liability' },
  { pattern: 'security.deepscan', level: 1, reason: 'Deep scan may trigger security alerts' },
  { pattern: 'system.restart', level: 2, reason: 'Restart interrupts running services' },
  { pattern: 'system.deploy', level: 3, reason: 'Deployment affects production' },
];

class KivoGuard {
  constructor(options = {}) {
    this.role = options.role || process.env.KIVO_ROLE || 'user';
    this.roleConfig = ROLES[this.role] || ROLES.user;
    this.sessionApprovals = new Set(); // Track one-time approvals
    this.auditLog = [];
  }

  // ── Permission Check ───────────────────────────────────────
  canExecute(intent) {
    const allowed = this.roleConfig.can.some(pattern => this.matchPattern(intent, pattern));
    return allowed;
  }

  matchPattern(intent, pattern) {
    if (pattern === '*') return true;
    if (pattern.endsWith('.*')) {
      const prefix = pattern.slice(0, -2);
      return intent.startsWith(prefix);
    }
    return intent === pattern;
  }

  // ── Approval Check ─────────────────────────────────────────
  requiresApproval(intent) {
    const action = SENSITIVE_ACTIONS.find(a => {
      if (a.pattern.endsWith('*')) {
        const prefix = a.pattern.slice(0, -1);
        return intent.startsWith(prefix);
      }
      return a.pattern === intent;
    });
    return action || null;
  }

  checkApproval(intent, forceConfirm = false) {
    if (!this.canExecute(intent)) {
      return { allowed: false, reason: `Role '${this.role}' cannot execute ${intent}` };
    }

    const sensitive = this.requiresApproval(intent);
    if (!sensitive) {
      return { allowed: true, requiresApproval: false };
    }

    const level = APPROVAL_LEVELS[sensitive.level];

    if (level === 'none') {
      return { allowed: true, requiresApproval: false };
    }

    if (level === 'notification') {
      return { allowed: true, requiresApproval: false, notify: sensitive.reason };
    }

    if (level === 'confirm_once') {
      if (this.sessionApprovals.has(intent) && !forceConfirm) {
        return { allowed: true, requiresApproval: false, preApproved: true };
      }
      return {
        allowed: false,
        requiresApproval: true,
        reason: sensitive.reason,
        action: intent,
        level: sensitive.level,
      };
    }

    if (level === 'confirm_always') {
      return {
        allowed: false,
        requiresApproval: true,
        reason: sensitive.reason,
        action: intent,
        level: sensitive.level,
      };
    }

    return { allowed: true, requiresApproval: false };
  }

  approve(intent) {
    this.sessionApprovals.add(intent);
    this.log('approval', { intent, role: this.role, timestamp: new Date().toISOString() });
    return { approved: true, intent };
  }

  // ── Audit Logging ──────────────────────────────────────────
  log(eventType, data) {
    const entry = {
      timestamp: new Date().toISOString(),
      event: eventType,
      role: this.role,
      ...data,
    };
    this.auditLog.push(entry);
    this.writeAuditLog(entry);
  }

  writeAuditLog(entry) {
    ensureDir(AUDIT_DIR);
    const line = JSON.stringify(entry) + '\n';
    fs.appendFileSync(AUDIT_FILE, line);
  }

  // ── Command Wrapper ────────────────────────────────────────
  async executeWithGuard(intent, handler, args = {}) {
    const check = this.checkApproval(intent);

    this.log('check', { intent, check });

    if (!check.allowed) {
      if (check.requiresApproval) {
        this.log('blocked', { intent, reason: check.reason });
        return {
          success: false,
          blocked: true,
          requiresApproval: true,
          reason: check.reason,
          action: intent,
        };
      }
      return {
        success: false,
        blocked: true,
        reason: check.reason,
      };
    }

    if (check.notify) {
      console.log(`[KIVO GUARD] Notification: ${check.notify}`);
    }

    try {
      const result = await handler(args);
      this.log('executed', { intent, result: typeof result === 'object' ? 'object' : result });
      return { success: true, result, guarded: true };
    } catch (e) {
      this.log('error', { intent, error: e.message });
      return { success: false, error: e.message };
    }
  }

  // ── Status ─────────────────────────────────────────────────
  getStatus() {
    return {
      role: this.role,
      maxApprovalLevel: this.roleConfig.maxApprovalLevel,
      sessionApprovals: this.sessionApprovals.size,
      auditEntries: this.auditLog.length,
      sensitiveActions: SENSITIVE_ACTIONS.length,
    };
  }
}

module.exports = { KivoGuard, ROLES, APPROVAL_LEVELS, SENSITIVE_ACTIONS };
