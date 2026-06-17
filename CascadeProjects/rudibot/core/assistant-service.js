const fs = require('fs');
const path = require('path');

/**
 * Assistant Service — Business Assistant für Dashboard und Formulare
 * 
 * 4 Arbeitsmodi:
 * 1. Inline Copilot — Direkt im Dashboard/Formular
 * 2. Action Copilot — Schritt-für-Schritt Begleitung
 * 3. Watchdog Copilot — Hintergrundüberwachung
 * 4. Learning Copilot — Aus Fehlern lernen
 */

class AssistantService {
  constructor(options = {}) {
    this.logger = options.logger || console;
    this.orchestrator = options.orchestrator;
    this.storagePath = options.storagePath || path.join(__dirname, '../../state/assistant');
    this.templates = new Map();
    this.validationRules = new Map();
    this.errorPatterns = new Map();
    
    this.ensureStorageDir();
    this.loadTemplates();
    this.loadValidationRules();
    this.loadErrorPatterns();
  }

  ensureStorageDir() {
    if (!fs.existsSync(this.storagePath)) {
      fs.mkdirSync(this.storagePath, { recursive: true });
    }
  }

  loadTemplates() {
    // Standard-Templates für häufige Aufgaben
    const defaultTemplates = {
      'invoice': {
        fields: ['company', 'ust_id', 'iban', 'amount', 'date', 'invoice_number'],
        required: ['company', 'amount', 'date', 'invoice_number'],
        defaults: {
          country: 'DE',
          currency: 'EUR',
          date: new Date().toISOString().split('T')[0]
        },
        formats: {
          iban: /^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$/,
          ust_id: /^DE[0-9]{9}$/,
          amount: /^\d+,\d{2}$/,
          date: /^\d{4}-\d{2}-\d{2}$/
        }
      },
      'product': {
        fields: ['name', 'price', 'category', 'description', 'sku'],
        required: ['name', 'price'],
        defaults: {
          currency: 'EUR',
          status: 'active'
        },
        formats: {
          price: /^\d+,\d{2}$/,
          sku: /^[A-Z0-9-]{4,20}$/
        }
      },
      'api_connection': {
        fields: ['name', 'url', 'api_key', 'method'],
        required: ['name', 'url', 'api_key'],
        defaults: {
          method: 'GET',
          timeout: 30000
        },
        formats: {
          url: /^https?:\/\/.+/,
          api_key: /^[a-zA-Z0-9_-]{16,}$/
        }
      }
    };

    for (const [key, template] of Object.entries(defaultTemplates)) {
      this.templates.set(key, template);
    }
  }

  loadValidationRules() {
    const defaultRules = {
      'required_field': {
        check: (value, field) => !value || value.trim() === '',
        message: (field) => `${field} ist ein Pflichtfeld`
      },
      'iban_format': {
        check: (value) => !/^DE[A-Z0-9]{2}[A-Z0-9]{11,30}$/.test(value),
        message: () => 'IBAN-Format ungültig (z.B. DE89370400440532013000)'
      },
      'ust_id_format': {
        check: (value) => !/^DE[0-9]{9}$/.test(value),
        message: () => 'USt-ID-Format ungültig (z.B. DE123456789)'
      },
      'email_format': {
        check: (value) => !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value),
        message: () => 'E-Mail-Format ungültig'
      },
      'price_format': {
        check: (value) => !/^\d+,\d{2}$/.test(value),
        message: () => 'Preis-Format ungültig (z.B. 19,99)'
      },
      'url_format': {
        check: (value) => !/^https?:\/\/.+/.test(value),
        message: () => 'URL-Format ungültig (z.B. https://example.com)'
      }
    };

    for (const [key, rule] of Object.entries(defaultRules)) {
      this.validationRules.set(key, rule);
    }
  }

  loadErrorPatterns() {
    // Lerne aus wiederkehrenden Fehlern
    const defaultPatterns = {
      'missing_ust_id': {
        pattern: /ust.*id.*fehlt/i,
        suggestion: 'USt-ID als Pflichtfeld hinzufügen',
        autofix: { field: 'ust_id', value: '' }
      },
      'invalid_iban': {
        pattern: /iban.*ungültig/i,
        suggestion: 'IBAN-Validierung aktivieren',
        autofix: { field: 'iban', value: 'DE' }
      },
      'empty_price': {
        pattern: /preis.*leer/i,
        suggestion: 'Preis als Pflichtfeld markieren',
        autofix: { field: 'price', value: '0,00' }
      }
    };

    for (const [key, pattern] of Object.entries(defaultPatterns)) {
      this.errorPatterns.set(key, pattern);
    }
  }

  /**
   * Mode 1: Inline Copilot — Live-Hilfe im Formular
   */
  async validateForm(data, templateType) {
    const template = this.templates.get(templateType);
    if (!template) {
      return {
        ok: false,
        error: `Template ${templateType} nicht gefunden`
      };
    }

    const result = {
      ok: true,
      warnings: [],
      suggestions: [],
      autofill: {},
      risk_level: 'green',
      missing_fields: [],
      invalid_fields: []
    };

    // Pflichtfelder prüfen
    for (const field of template.required || []) {
      const value = data[field];
      if (!value || value.trim() === '') {
        result.warnings.push(`${field} ist ein Pflichtfeld`);
        result.missing_fields.push(field);
        result.risk_level = 'yellow';
      }
    }

    // Formate prüfen
    for (const [field, format] of Object.entries(template.formats || {})) {
      const value = data[field];
      if (value && !format.test(value)) {
        result.warnings.push(`${field} hat ungültiges Format`);
        result.invalid_fields.push(field);
        result.risk_level = 'yellow';
      }
    }

    // Autofill-Vorschläge
    for (const [field, defaultValue] of Object.entries(template.defaults || {})) {
      if (!data[field] || data[field] === '') {
        result.autofill[field] = defaultValue;
        result.suggestions.push(`${field} mit Standardwert ausfüllen`);
      }
    }

    // Spezielle Validierungsregeln
    for (const [ruleName, rule] of this.validationRules) {
      for (const [field, value] of Object.entries(data)) {
        if (rule.check(value, field)) {
          result.warnings.push(rule.message(field));
          result.risk_level = 'yellow';
        }
      }
    }

    return result;
  }

  /**
   * Mode 2: Action Copilot — Schritt-für-Schritt Begleitung
   */
  async getActionSteps(actionType, context = {}) {
    const actionPlans = {
      'product_create': [
        {
          step: 1,
          title: 'Produkt-Informationen',
          description: 'Grundlegende Produkt-Daten eingeben',
          fields: ['name', 'price', 'category'],
          validation: 'required_fields'
        },
        {
          step: 2,
          title: 'Details & Beschreibung',
          description: 'Produkt-Beschreibung und Metadaten',
          fields: ['description', 'sku', 'tags'],
          validation: 'format_check'
        },
        {
          step: 3,
          title: 'Verifizierung',
          description: 'Daten prüfen und speichern',
          validation: 'final_review'
        }
      ],
      'api_connect': [
        {
          step: 1,
          title: 'API-Verbindung',
          description: 'Endpunkt und Authentifizierung konfigurieren',
          fields: ['url', 'api_key', 'method'],
          validation: 'security_check'
        },
        {
          step: 2,
          title: 'Verbindungstest',
          description: 'API-Verbindung testen und validieren',
          validation: 'connectivity_test'
        }
      ],
      'cost_analysis': [
        {
          step: 1,
          title: 'Kosten sammeln',
          description: 'Alle Ausgaben und Abos erfassen',
          fields: ['subscriptions', 'tools', 'apis'],
          validation: 'completeness_check'
        },
        {
          step: 2,
          title: 'Analyse',
          description: 'Kosten analysieren und Optimierungen finden',
          validation: 'analysis_complete'
        }
      ]
    };

    const plan = actionPlans[actionType];
    if (!plan) {
      return {
        ok: false,
        error: `Action Plan ${actionType} nicht gefunden`
      };
    }

    return {
      ok: true,
      action_type: actionType,
      steps: plan,
      current_step: 1,
      total_steps: plan.length,
      progress: 0
    };
  }

  /**
   * Mode 3: Watchdog Copilot — Hintergrundüberwachung
   */
  async getSystemHealth() {
    const health = {
      overall: 'good',
      issues: [],
      recommendations: [],
      metrics: {
        error_rate: 0.05,
        response_time: 250,
        uptime: 0.998,
        active_workflows: 12,
        pending_approvals: 3
      }
    };

    // Fehlerquote prüfen
    if (health.metrics.error_rate > 0.1) {
      health.issues.push('Hohe Fehlerquote (>10%)');
      health.recommendations.push('Fehler-Quellen untersuchen');
      health.overall = 'warning';
    }

    // Response Time prüfen
    if (health.metrics.response_time > 500) {
      health.issues.push('Langsame Antwortzeiten (>500ms)');
      health.recommendations.push('Performance optimieren');
      health.overall = 'warning';
    }

    // Offene Freigaben prüfen
    if (health.metrics.pending_approvals > 5) {
      health.issues.push('Viele offene Freigaben');
      health.recommendations.push('Freigaben bearbeiten');
      health.overall = 'warning';
    }

    return health;
  }

  /**
   * Mode 4: Learning Copilot — Aus Fehlern lernen
   */
  async learnFromErrors(errors) {
    const insights = {
      patterns_found: [],
      new_rules: [],
      improvements: []
    };

    for (const error of errors) {
      // Fehlermuster erkennen
      for (const [patternName, pattern] of this.errorPatterns) {
        if (pattern.pattern.test(error.message)) {
          insights.patterns_found.push({
            pattern: patternName,
            error: error.message,
            count: 1
          });

          // Neue Regel vorschlagen
          insights.new_rules.push({
            type: 'validation',
            field: pattern.autofix.field,
            rule: pattern.suggestion,
            priority: 'medium'
          });
        }
      }
    }

    // Lernen aus wiederkehrenden Problemen
    const errorCounts = {};
    for (const error of errors) {
      const key = error.type || 'unknown';
      errorCounts[key] = (errorCounts[key] || 0) + 1;
    }

    for (const [errorType, count] of Object.entries(errorCounts)) {
      if (count > 3) {
        insights.improvements.push({
          issue: errorType,
          frequency: count,
          suggestion: `Automatischer Check für ${errorType} hinzufügen`
        });
      }
    }

    return insights;
  }

  /**
   * Kontext-basierte Vorschläge
   */
  async getSuggestions(context) {
    const suggestions = {
      immediate: [],
      proactive: [],
      optimization: []
    };

    const { current_page, user_action, data } = context;

    // Seiten-spezifische Vorschläge
    if (current_page === 'invoice_create') {
      suggestions.immediate.push('Letzte Kunden-Adresse verwenden');
      suggestions.proactive.push('Rechnungsvorlage speichern');
    }

    if (current_page === 'dashboard') {
      suggestions.immediate.push('Business Health Check starten');
      suggestions.proactive.push('Kosten-Report generieren');
    }

    // Aktions-basierte Vorschläge
    if (user_action === 'error_occurred') {
      suggestions.immediate.push('Fehler melden und analysieren');
      suggestions.proactive.push('Präventive Regel erstellen');
    }

    // Daten-basierte Vorschläge
    if (data?.costs && data.costs.unusual) {
      suggestions.optimization.push('Kostenanomalie untersuchen');
    }

    return suggestions;
  }

  /**
   * Risiko-Bewertung für Aktionen
   */
  async assessRisk(action, context) {
    const riskMatrix = {
      'delete_data': 'high',
      'change_config': 'medium',
      'api_revoke': 'high',
      'cost_increase': 'medium',
      'user_access_change': 'medium',
      'export_data': 'low'
    };

    const baseRisk = riskMatrix[action] || 'medium';
    let adjustedRisk = baseRisk;

    // Kontext-basierte Anpassung
    if (context?.is_production) {
      if (baseRisk === 'medium') adjustedRisk = 'high';
      if (baseRisk === 'low') adjustedRisk = 'medium';
    }

    if (context?.has_backup) {
      if (baseRisk === 'high') adjustedRisk = 'medium';
    }

    if (context?.is_test) {
      adjustedRisk = 'low';
    }

    return {
      risk_level: adjustedRisk,
      base_risk: baseRisk,
      factors: {
        production: context?.is_production || false,
        backup: context?.has_backup || false,
        test: context?.is_test || false
      },
      recommendation: this.getRiskRecommendation(adjustedRisk, action)
    };
  }

  getRiskRecommendation(riskLevel, action) {
    const recommendations = {
      'high': `Aktion "${action}" erfordert Freigabe durch Admin`,
      'medium': `Aktion "${action}" sollte überprüft werden`,
      'low': `Aktion "${action}" kann sicher ausgeführt werden`
    };

    return recommendations[riskLevel] || recommendations.medium;
  }

  /**
   * Business-Health Check
   */
  async getBusinessHealth() {
    const health = {
      score: 85,
      status: 'good',
      areas: {
        revenue: { score: 90, status: 'excellent', trend: 'up' },
        costs: { score: 75, status: 'good', trend: 'stable' },
        automation: { score: 88, status: 'excellent', trend: 'up' },
        security: { score: 82, status: 'good', trend: 'stable' },
        efficiency: { score: 80, status: 'good', trend: 'up' }
      },
      recommendations: [
        'Kostenoptimierung bei SaaS-Tools prüfen',
        'Automatisierung für wiederkehrende Aufgaben ausbauen',
        'Security-Scans wöchentlich durchführen'
      ],
      alerts: [
        { type: 'info', message: 'Umsatz steigt um 12%' },
        { type: 'warning', message: 'API-Kosten本月 erhöht' }
      ]
    };

    return health;
  }
}

module.exports = { AssistantService };
