const fs = require('fs');
const path = require('path');

class RiskEngine {
  constructor(options = {}) {
    this.configPath = options.configPath || path.join(__dirname, '../../config/risk-policies.json');
    this.policies = this.loadPolicies();
    this.logger = options.logger || console;
  }

  loadPolicies() {
    try {
      if (fs.existsSync(this.configPath)) {
        const content = fs.readFileSync(this.configPath, 'utf8');
        return JSON.parse(content);
      }
    } catch (err) {
      this.logger.warn?.('risk-engine.policies.load_failed', { error: err.message });
    }

    // Default policies if file doesn't exist or is invalid
    return {
      auto_allow: [
        'health_check',
        'status_report',
        'log_scan',
        'safe_sync',
        'usage_analysis',
        'daily_report',
        'monitoring_check',
        'api_validation'
      ],
      approval_required: [
        'cancel_subscription',
        'rotate_key',
        'notify_external',
        'change_config',
        'billing_action',
        'security_scan',
        'cost_analysis',
        'subscription_audit',
        'key_rotation_prepare'
      ],
      hard_blocked: [
        'delete_account',
        'revoke_api_full_access',
        'move_money',
        'external_communication',
        'production_key_change',
        'data_deletion',
        'account_termination'
      ]
    };
  }

  classify(job) {
    const { action, source, type, payload } = job;

    // Direct action matching
    if (this.policies.hard_blocked.includes(action)) {
      return 'red';
    }

    if (this.policies.auto_allow.includes(action)) {
      return 'green';
    }

    if (this.policies.approval_required.includes(action)) {
      return 'yellow';
    }

    // Pattern-based classification for dynamic actions
    const lowerAction = action.toLowerCase();
    
    // High-risk patterns
    if (this.matchesPattern(lowerAction, [
      'delete', 'remove', 'terminate', 'cancel', 'destroy',
      'revoke', 'disable', 'suspend', 'block', 'purge'
    ])) {
      return 'red';
    }

    // Medium-risk patterns
    if (this.matchesPattern(lowerAction, [
      'rotate', 'update', 'modify', 'change', 'edit',
      'configure', 'adjust', 'migrate', 'replace'
    ])) {
      return 'yellow';
    }

    // Low-risk patterns
    if (this.matchesPattern(lowerAction, [
      'check', 'validate', 'verify', 'scan', 'monitor',
      'report', 'analyze', 'review', 'audit', 'sync'
    ])) {
      return 'green';
    }

    // Source-based risk adjustment
    if (source === 'system' || source === 'scheduler') {
      // System-initiated jobs are generally lower risk
      return 'green';
    }

    if (source === 'external_api' || source === 'unknown') {
      // External or unknown sources require caution
      return 'yellow';
    }

    // Type-based classification
    if (type === 'event') {
      // Events are typically internal system notifications
      return 'green';
    }

    if (type === 'command' && source === 'admin') {
      // Admin commands get approval by default
      return 'yellow';
    }

    // Default to yellow for safety
    return 'yellow';
  }

  matchesPattern(action, patterns) {
    return patterns.some(pattern => action.includes(pattern));
  }

  updatePolicies(newPolicies) {
    try {
      this.policies = { ...this.policies, ...newPolicies };
      
      // Ensure directory exists
      const dir = path.dirname(this.configPath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      
      fs.writeFileSync(this.configPath, JSON.stringify(this.policies, null, 2));
      this.logger.info?.('risk-engine.policies.updated', { path: this.configPath });
      return true;
    } catch (err) {
      this.logger.error?.('risk-engine.policies.update_failed', { error: err.message });
      return false;
    }
  }

  getPolicies() {
    return { ...this.policies };
  }

  explainRisk(job) {
    const riskLevel = this.classify(job);
    let reason = '';

    const { action, source, type } = job;

    if (this.policies.hard_blocked.includes(action)) {
      reason = `Action '${action}' is in hard-blocked list`;
    } else if (this.policies.auto_allow.includes(action)) {
      reason = `Action '${action}' is in auto-allow list`;
    } else if (this.policies.approval_required.includes(action)) {
      reason = `Action '${action}' is in approval-required list`;
    } else {
      reason = `Pattern-based classification for action '${action}' from source '${source}'`;
    }

    return {
      riskLevel,
      reason,
      policies: this.policies
    };
  }
}

module.exports = { RiskEngine };
