/**
 * KIVO Intents — Intent definitions and handlers
 * Centralized intent management for KIVO
 */

class KivoIntents {
  constructor() {
    this.intents = new Map();
    this.setupIntents();
  }

  setupIntents() {
    // Home Control Intents
    this.intents.set('home.control', {
      patterns: ['licht an', 'licht aus', 'lampe an', 'lampe aus', 'schalter an', 'schalter aus'],
      entities: ['device', 'action'],
      handler: this.handleHomeControl.bind(this)
    });

    this.intents.set('home.climate', {
      patterns: ['temperatur', 'heizung', 'thermostat', 'klima'],
      entities: ['device', 'temperature'],
      handler: this.handleHomeClimate.bind(this)
    });

    this.intents.set('home.timer', {
      patterns: ['timer', 'wecker', 'alarm', 'countdown'],
      entities: ['duration'],
      handler: this.handleHomeTimer.bind(this)
    });

    this.intents.set('home.access', {
      patterns: ['tor', 'garage', 'tür', 'schloss', 'öffnen', 'schließen'],
      entities: ['device', 'action'],
      handler: this.handleHomeAccess.bind(this)
    });

    // Finance Intents
    this.intents.set('finance.subscriptions', {
      patterns: ['abo', 'vertrag', 'kündigen', 'subscription', 'cancel'],
      entities: ['action', 'provider'],
      handler: this.handleFinanceSubscriptions.bind(this)
    });

    this.intents.set('finance.tax', {
      patterns: ['steuer', 'tax', 'elster', 'finanz'],
      entities: ['action', 'year'],
      handler: this.handleFinanceTax.bind(this)
    });

    // Security Intents
    this.intents.set('security.scan', {
      patterns: ['scan', 'audit', 'security', 'sicherheit', 'deepscan'],
      entities: ['action'],
      handler: this.handleSecurityScan.bind(this)
    });

    // Report Intents
    this.intents.set('report.status', {
      patterns: ['status', 'übersicht', 'bericht', 'report', 'was ist'],
      entities: ['scope'],
      handler: this.handleReportStatus.bind(this)
    });
  }

  // ── Intent Matching ────────────────────────────────────────
  matchIntent(text) {
    const lower = text.toLowerCase();
    let bestMatch = null;
    let bestScore = 0;

    for (const [intentId, intent] of this.intents) {
      const score = this.calculateMatchScore(lower, intent.patterns);
      if (score > bestScore && score > 0.5) {
        bestMatch = { id: intentId, intent, score };
        bestScore = score;
      }
    }

    return bestMatch;
  }

  calculateMatchScore(text, patterns) {
    let score = 0;
    for (const pattern of patterns) {
      if (text.includes(pattern.toLowerCase())) {
        score += 1 / patterns.length;
      }
    }
    return score;
  }

  // ── Entity Extraction ─────────────────────────────────────
  extractEntities(text, intentId) {
    const intent = this.intents.get(intentId);
    if (!intent) return {};

    const entities = {};
    const lower = text.toLowerCase();

    for (const entity of intent.entities) {
      switch (entity) {
        case 'device':
          entities.device = this.extractDevice(lower);
          break;
        case 'action':
          entities.action = this.extractAction(lower);
          break;
        case 'temperature':
          entities.temperature = this.extractTemperature(lower);
          break;
        case 'duration':
          entities.duration = this.extractDuration(lower);
          break;
        case 'provider':
          entities.provider = this.extractProvider(lower);
          break;
        case 'year':
          entities.year = this.extractYear(lower);
          break;
        case 'scope':
          entities.scope = this.extractScope(lower);
          break;
      }
    }

    return entities;
  }

  extractDevice(text) {
    const devices = ['licht', 'lampe', 'schalter', 'steckdose', 'heizung', 'thermostat', 'tor', 'garage', 'tür'];
    for (const device of devices) {
      if (text.includes(device)) return device;
    }
    return null;
  }

  extractAction(text) {
    if (text.includes('an') || text.includes('ein') || text.includes('öffnen')) return 'on';
    if (text.includes('aus') || text.includes('aus') || text.includes('schließen')) return 'off';
    if (text.includes('toggle') || text.includes('wechseln')) return 'toggle';
    return null;
  }

  extractTemperature(text) {
    const match = text.match(/(\d+)\s*(grad|°|celsius)/i);
    return match ? parseInt(match[1]) : null;
  }

  extractDuration(text) {
    const match = text.match(/(\d+)\s*(min|minute|stunde|hour|sek|sec)/i);
    if (!match) return null;
    
    const value = parseInt(match[1]);
    const unit = match[2].toLowerCase();
    
    if (unit.includes('min')) return value;
    if (unit.includes('stunde') || unit.includes('hour')) return value * 60;
    if (unit.includes('sek') || unit.includes('sec')) return Math.floor(value / 60);
    
    return value;
  }

  extractProvider(text) {
    const providers = ['netflix', 'spotify', 'adobe', 'amazon', 'google', 'microsoft'];
    for (const provider of providers) {
      if (text.includes(provider)) return provider;
    }
    return null;
  }

  extractYear(text) {
    const match = text.match(/(20\d{2})/);
    return match ? parseInt(match[1]) : new Date().getFullYear();
  }

  extractScope(text) {
    if (text.includes('system')) return 'system';
    if (text.includes('finanz') || text.includes('geld')) return 'finance';
    if (text.includes('security') || text.includes('sicherheit')) return 'security';
    if (text.includes('home') || text.includes('haus')) return 'home';
    return 'all';
  }

  // ── Intent Handlers ───────────────────────────────────────
  async handleHomeControl(entities) {
    const { device, action } = entities;
    return {
      type: 'home',
      action: 'control',
      device: device || 'unknown',
      action: action || 'toggle',
      message: `🏠 Home Control: ${device || 'Gerät'} ${action || 'schalten'}`
    };
  }

  async handleHomeClimate(entities) {
    const { device, temperature } = entities;
    return {
      type: 'home',
      action: 'climate',
      device: device || 'thermostat',
      temperature,
      message: `🌡️ Klima: ${temperature ? temperature + '°C' : 'wird angepasst'}`
    };
  }

  async handleHomeTimer(entities) {
    const { duration } = entities;
    const minutes = duration || 10;
    return {
      type: 'home',
      action: 'timer',
      timer: { minutes },
      message: `⏰ Timer für ${minutes} Minuten gestellt`
    };
  }

  async handleHomeAccess(entities) {
    const { device, action } = entities;
    return {
      type: 'home',
      action: 'access',
      device: device || 'garage',
      action: action || 'toggle',
      message: `🔓 Zugang: ${device || 'Tor'} ${action || 'steuern'}`
    };
  }

  async handleFinanceSubscriptions(entities) {
    const { action, provider } = entities;
    return {
      type: 'agent',
      action: 'subscription',
      provider,
      requiresApproval: action === 'kündigen',
      message: `💰 Abo-Management: ${action || 'anzeigen'}${provider ? ' für ' + provider : ''}`
    };
  }

  async handleFinanceTax(entities) {
    const { action, year } = entities;
    return {
      type: 'agent',
      action: 'finance',
      year: year || new Date().getFullYear(),
      requiresApproval: action === 'export',
      message: `📋 Steuer: ${action || 'status'} ${year || 'heute'}`
    };
  }

  async handleSecurityScan(entities) {
    return {
      type: 'agent',
      action: 'security',
      message: '🔍 Security Scan wird gestartet...'
    };
  }

  async handleReportStatus(entities) {
    const { scope } = entities;
    return {
      type: 'agent',
      action: 'report',
      scope,
      message: `📊 Status Report: ${scope || 'alles'}`
    };
  }

  // ── Public API ───────────────────────────────────────────
  async processIntent(text) {
    const match = this.matchIntent(text);
    if (!match) {
      return {
        type: 'unknown',
        action: 'fallback',
        message: '🤔 Das habe ich nicht verstanden'
      };
    }

    const entities = this.extractEntities(text, match.id);
    const result = await match.intent.handler(entities);
    
    return {
      ...result,
      intentId: match.id,
      confidence: match.score,
      entities
    };
  }

  listIntents() {
    return Array.from(this.intents.keys());
  }
}

module.exports = { KivoIntents };
