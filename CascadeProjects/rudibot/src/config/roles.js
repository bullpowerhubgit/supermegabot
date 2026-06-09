/**
 * Roles Configuration — Permission definitions for KIVO Guard
 */

const ROLES = {
  guest: {
    name: 'Guest',
    description: 'Limited access to read-only features',
    permissions: {
      commands: ['start', 'help', 'status', 'kivo'],
      intents: ['system.status', 'home.status'],
      actions: ['dashboard.query'],
      canApprove: false,
      canCancel: false,
      maxApprovalLevel: 0
    }
  },

  user: {
    name: 'User',
    description: 'Standard user with full read and limited write access',
    permissions: {
      commands: ['start', 'help', 'status', 'health', 'kivo', 'kivo-say', 'kivo-home',
        'fin-grid', 'subs', 'spend', 'tax', 'home'],
      intents: ['system.status', 'home.*', 'finance.overview', 'finance.subscriptions',
        'finance.spend', 'finance.tax', 'agent.report', 'agent.security'],
      actions: ['dashboard.query', 'dashboard.status', 'finance.query', 'home.control',
        'home.climate', 'home.timer', 'home.access'],
      canApprove: false,
      canCancel: true,
      maxApprovalLevel: 1
    }
  },

  admin: {
    name: 'Admin',
    description: 'Full system access including sensitive operations',
    permissions: {
      commands: ['*'],
      intents: ['*'],
      actions: ['*'],
      canApprove: true,
      canCancel: true,
      maxApprovalLevel: 3
    }
  },

  owner: {
    name: 'Owner',
    description: 'System owner with unrestricted access',
    permissions: {
      commands: ['*'],
      intents: ['*'],
      actions: ['*'],
      canApprove: true,
      canCancel: true,
      maxApprovalLevel: 3,
      bypassApproval: true
    }
  }
};

const APPROVAL_LEVELS = {
  0: { name: 'none', description: 'No approval needed' },
  1: { name: 'notification', description: 'Notify only, no block' },
  2: { name: 'confirm_once', description: 'Confirm once per session' },
  3: { name: 'confirm_always', description: 'Always confirm' }
};

const SENSITIVE_ACTIONS = [
  {
    pattern: 'finance.subscription',
    level: 2,
    reason: 'Subscription cancellation is irreversible and may affect services',
    requiresRole: ['admin', 'owner']
  },
  {
    pattern: 'finance.tax',
    level: 2,
    reason: 'Tax export involves legal liability and financial reporting',
    requiresRole: ['admin', 'owner']
  },
  {
    pattern: 'security.scan',
    level: 1,
    reason: 'Security scan may trigger alerts or affect system performance',
    requiresRole: ['user', 'admin', 'owner']
  },
  {
    pattern: 'system.restart',
    level: 2,
    reason: 'Restart interrupts all running services',
    requiresRole: ['admin', 'owner']
  },
  {
    pattern: 'system.deploy',
    level: 3,
    reason: 'Deployment affects production environment',
    requiresRole: ['owner']
  },
  {
    pattern: 'system.cleanup',
    level: 2,
    reason: 'Cleanup may delete important data',
    requiresRole: ['admin', 'owner']
  },
  {
    pattern: 'home.access',
    level: 2,
    reason: 'Access control affects physical security',
    requiresRole: ['user', 'admin', 'owner']
  },
  {
    pattern: 'dashboard.export',
    level: 1,
    reason: 'Data export may contain sensitive information',
    requiresRole: ['admin', 'owner']
  }
];

function getRole(roleName) {
  return ROLES[roleName] || ROLES.user;
}

function canExecute(roleName, intent) {
  const role = getRole(roleName);
  if (!role) return false;

  const permissions = role.permissions;
  if (permissions.intents.includes('*')) return true;

  // Check exact match
  if (permissions.intents.includes(intent)) return true;

  // Check wildcard match
  return permissions.intents.some(pattern => {
    if (pattern.endsWith('.*')) {
      const prefix = pattern.slice(0, -2);
      return intent.startsWith(prefix);
    }
    return pattern === intent;
  });
}

function requiresApproval(intent, roleName) {
  const action = SENSITIVE_ACTIONS.find(a => {
    if (a.pattern.endsWith('*')) {
      const prefix = a.pattern.slice(0, -1);
      return intent.startsWith(prefix);
    }
    return a.pattern === intent;
  });

  if (!action) return null;

  // Check if user's role can execute this action
  const role = getRole(roleName);
  if (action.requiresRole && !action.requiresRole.includes(roleName)) {
    return {
      ...action,
      blocked: true,
      reason: `Action requires role: ${action.requiresRole.join(' or ')}`
    };
  }

  // Owner can bypass
  if (role.permissions.bypassApproval) {
    return { ...action, bypassed: true };
  }

  return action;
}

module.exports = {
  ROLES,
  APPROVAL_LEVELS,
  SENSITIVE_ACTIONS,
  getRole,
  canExecute,
  requiresApproval
};
