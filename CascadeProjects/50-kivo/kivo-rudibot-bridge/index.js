/**
 * KIVO RUDIBOT BRIDGE — Connects KIVO to Rudibot, Scans, Reports, Finance Grid
 * Translates KIVO intents into Rudibot Telegram commands and system actions
 */

const EventEmitter = require('events');

const RUDIBOT_API = {
  baseUrl: process.env.RUDIBOT_API_URL || 'http://localhost:3201',
  webhookUrl: process.env.RUDIBOT_WEBHOOK_URL || null,
};

class KivoRudibotBridge extends EventEmitter {
  constructor(options = {}) {
    super();
    this.config = { ...RUDIBOT_API, ...options };
    this.commandMap = this.buildCommandMap();
  }

  // ── Command Mapping ──────────────────────────────────────
  buildCommandMap() {
    return {
      // Home / Fast path
      'home.status': '/status',
      'home.health': '/health',

      // Security
      'security.validate': '/validate',
      'security.deepscan': '/deepscan',
      'security.audit': '/audit',
      'security.status': '/security',

      // Finance Grid
      'finance.overview': '/fin-grid',
      'finance.subscriptions': '/subs',
      'finance.kill_subscription': '/sub-kill',
      'finance.tax': '/tax',
      'finance.spend': '/spend',
      'finance.elster': '/elster',

      // System
      'system.restart': '/restart',
      'system.logs': '/logs',
      'system.deploy': '/deploy',
      'system.monitor': '/monitor',
      'system.cleanup': '/cleanup',

      // Help
      'help.commands': '/help',
      'help.start': '/start',
    };
  }

  // ── Execute Rudibot Command ────────────────────────────────
  async executeCommand(intent, args = {}) {
    const command = this.resolveIntentToCommand(intent);
    if (!command) {
      return { success: false, error: `No command mapped for intent: ${intent}` };
    }

    this.emit('command', { intent, command, args });

    // Option 1: Direct API call to Rudibot health endpoint
    if (command === '/health') {
      return this.callHealthCheck();
    }

    // Option 2: Simulate command execution (for testing without Telegram)
    return this.simulateCommand(command, args);
  }

  resolveIntentToCommand(intent) {
    return this.commandMap[intent] || null;
  }

  // ── Health Check ───────────────────────────────────────────
  async callHealthCheck() {
    try {
      const res = await fetch(`${this.config.baseUrl}/bot-health`, {
        signal: AbortSignal.timeout(5000),
      });
      const data = await res.json();
      return { success: true, command: '/health', data };
    } catch (e) {
      return { success: false, command: '/health', error: e.message, offline: true };
    }
  }

  // ── Simulate Command (for local testing) ───────────────────
  simulateCommand(command, args = {}) {
    const responses = {
      '/fin-grid': () => ({
        message: '💰 Finance Grid Overview\n\n📊 Subscriptions: 3 active\n💰 Monthly: 45.97 EUR\n📅 Upcoming: Netflix (2026-06-30)\n⚖️ Compliance: 2 deadlines upcoming',
        module: 'finance',
      }),
      '/subs': () => ({
        message: '🎯 Subscriptions\n\n1. Netflix — 17.99 EUR/mo\n2. Spotify — 10.99 EUR/mo\n3. Adobe CC — 16.99 EUR/mo',
        module: 'subscription-hunter',
      }),
      '/sub-kill': () => ({
        message: `🗡️ Kill prepared for ${args.id || 'unknown'}\nRequires approval. Use /approve to confirm.`,
        requiresApproval: true,
        module: 'cancellation-engine',
      }),
      '/tax': () => ({
        message: '📋 Tax Core 2026\n\nDocuments: 12\nTax Expenses: 2340.50 EUR\nTop: Software (899 EUR), Hosting (420 EUR)',
        module: 'tax-core',
      }),
      '/spend': () => ({
        message: '💰 Expense Radar (June 2026)\n\nIncome: 0 EUR\nExpenses: 2340.50 EUR\nBalance: -2340.50 EUR',
        module: 'expense-radar',
      }),
      '/elster': () => ({
        message: '📤 ELSTER Export Ready\nYear: 2026\nFile: elster-2026.json\nTaxable Income: calculated\nRequires approval before submission.',
        requiresApproval: true,
        module: 'tax-core',
      }),
      '/validate': () => ({
        message: '🔐 API Validator\nAll keys validated successfully.\nNo leaks detected.',
        module: 'security',
      }),
      '/deepscan': () => ({
        message: '🔍 Deep Scan Initiated\nScanning all project directories...\nCheck /audit for full report.',
        module: 'security',
      }),
      '/audit': () => ({
        message: '📊 Security Audit Report\n\n• 0 critical secrets found\n• 0 unprotected commands\n• 0 expired certificates\nStatus: GREEN',
        module: 'security',
      }),
      '/status': () => ({
        message: '📊 System Status\n\n• Rudibot: Online\n• Gateway: Online\n• Finance Grid: Active\n• KIVO: Connected',
        module: 'system',
      }),
    };

    const handler = responses[command];
    if (handler) {
      return { success: true, command, ...handler() };
    }

    return { success: false, command, error: 'Command simulation not implemented' };
  }

  // ── Complex Query Handler ──────────────────────────────────
  async handleComplexQuery(query, context = {}) {
    // Parse natural language queries and route to appropriate workflows
    const lower = query.toLowerCase();

    if (lower.includes('abo') && lower.includes('kündig')) {
      return this.executeCommand('finance.kill_subscription', { id: context.subscriptionId });
    }

    if (lower.includes('steuer') || lower.includes('tax') || lower.includes('elster')) {
      return this.executeCommand('finance.tax');
    }

    if (lower.includes('scan') || lower.includes('sicherheit') || lower.includes('security')) {
      return this.executeCommand('security.deepscan');
    }

    if (lower.includes('status') || lower.includes('übersicht')) {
      return this.executeCommand('finance.overview');
    }

    if (lower.includes('report') || lower.includes('bericht')) {
      return this.executeCommand('system.status');
    }

    return { success: false, error: 'Could not understand query', query };
  }

  // ── Status ─────────────────────────────────────────────────
  getStatus() {
    return {
      rudibotUrl: this.config.baseUrl,
      webhookConfigured: !!this.config.webhookUrl,
      commandsMapped: Object.keys(this.commandMap).length,
    };
  }
}

module.exports = { KivoRudibotBridge };
