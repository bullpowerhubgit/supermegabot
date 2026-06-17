/**
 * Feature Flags — Enable/disable KIVO features dynamically
 * Controls which capabilities are active per environment/role
 */

const FEATURE_FLAGS = {
  // Core Features
  voice: {
    enabled: true,
    description: 'Voice message processing and TTS responses',
    requires: ['WHISPER_PATH'],
    roles: ['user', 'admin', 'owner'],
    environments: ['development', 'production']
  },

  voice_tts: {
    enabled: true,
    description: 'Text-to-speech responses in Telegram',
    requires: ['PIPER_PATH'],
    roles: ['user', 'admin', 'owner'],
    environments: ['development', 'production']
  },

  // Home Assistant
  homeassistant: {
    enabled: false,
    description: 'Smart home device control via Home Assistant',
    requires: ['HOME_ASSISTANT_URL', 'HOME_ASSISTANT_TOKEN'],
    roles: ['user', 'admin', 'owner'],
    environments: ['development', 'production']
  },

  homeassistant_discovery: {
    enabled: false,
    description: 'Automatic device discovery from Home Assistant',
    requires: ['homeassistant'],
    roles: ['admin', 'owner'],
    environments: ['development', 'production']
  },

  // Finance Grid
  finance_grid: {
    enabled: true,
    description: 'Finance Grid integration for subscriptions and expenses',
    requires: [],
    roles: ['user', 'admin', 'owner'],
    environments: ['development', 'production']
  },

  finance_subscriptions: {
    enabled: true,
    description: 'Subscription management and cancellation',
    requires: ['finance_grid'],
    roles: ['user', 'admin', 'owner'],
    environments: ['development', 'production']
  },

  finance_tax: {
    enabled: true,
    description: 'Tax preparation and ELSTER export',
    requires: ['finance_grid'],
    roles: ['admin', 'owner'],
    environments: ['development', 'production']
  },

  finance_elster: {
    enabled: false,
    description: 'Direct ELSTER portal integration',
    requires: ['finance_tax', 'ELSTER_CREDENTIALS'],
    roles: ['owner'],
    environments: ['production']
  },

  // Security
  security_scan: {
    enabled: true,
    description: 'Deep security scanning capabilities',
    requires: [],
    roles: ['admin', 'owner'],
    environments: ['development', 'production']
  },

  security_api_validator: {
    enabled: true,
    description: 'API key validation and leak detection',
    requires: ['security_scan'],
    roles: ['admin', 'owner'],
    environments: ['development', 'production']
  },

  // Workflows
  workflows: {
    enabled: true,
    description: 'Multi-step workflow execution',
    requires: [],
    roles: ['user', 'admin', 'owner'],
    environments: ['development', 'production']
  },

  workflow_morning_briefing: {
    enabled: true,
    description: 'Automated morning status briefing',
    requires: ['workflows'],
    roles: ['user', 'admin', 'owner'],
    environments: ['development', 'production']
  },

  workflow_evening_mode: {
    enabled: true,
    description: 'Home evening mode activation',
    requires: ['workflows', 'homeassistant'],
    roles: ['user', 'admin', 'owner'],
    environments: ['development', 'production']
  },

  // Legal
  legal_compliance: {
    enabled: true,
    description: 'GDPR, AGB, and compliance checking',
    requires: [],
    roles: ['admin', 'owner'],
    environments: ['development', 'production']
  },

  legal_document_generation: {
    enabled: true,
    description: 'Automated legal document generation',
    requires: ['legal_compliance'],
    roles: ['admin', 'owner'],
    environments: ['development', 'production']
  },

  // Dashboard
  dashboard: {
    enabled: true,
    description: 'Status dashboard and reporting',
    requires: [],
    roles: ['user', 'admin', 'owner'],
    environments: ['development', 'production']
  },

  dashboard_metrics: {
    enabled: false,
    description: 'Detailed metrics and analytics',
    requires: ['dashboard'],
    roles: ['admin', 'owner'],
    environments: ['development', 'production']
  },

  // Advanced
  memory_persistence: {
    enabled: true,
    description: 'Persistent user memory across sessions',
    requires: [],
    roles: ['user', 'admin', 'owner'],
    environments: ['development', 'production']
  },

  advanced_nlu: {
    enabled: false,
    description: 'Advanced natural language understanding',
    requires: ['OPENAI_API_KEY'],
    roles: ['admin', 'owner'],
    environments: ['production']
  },

  webhook_integration: {
    enabled: false,
    description: 'External webhook triggers and callbacks',
    requires: ['WEBHOOK_SECRET'],
    roles: ['admin', 'owner'],
    environments: ['production']
  }
};

class FeatureFlags {
  constructor(options = {}) {
    this.flags = { ...FEATURE_FLAGS, ...options.overrides };
    this.environment = options.environment || process.env.NODE_ENV || 'development';
  }

  isEnabled(featureName, userRole = null) {
    const feature = this.flags[featureName];
    if (!feature) return false;

    // Check environment
    if (!feature.environments.includes(this.environment)) {
      return false;
    }

    // Check role
    if (userRole && !feature.roles.includes(userRole)) {
      return false;
    }

    // Check dependencies
    if (feature.requires) {
      for (const dep of feature.requires) {
        if (dep.startsWith('ENV:')) {
          const envVar = dep.replace('ENV:', '');
          if (!process.env[envVar]) return false;
        } else if (!this.isEnabled(dep, userRole)) {
          return false;
        }
      }
    }

    return feature.enabled;
  }

  enable(featureName) {
    if (this.flags[featureName]) {
      this.flags[featureName].enabled = true;
    }
  }

  disable(featureName) {
    if (this.flags[featureName]) {
      this.flags[featureName].enabled = false;
    }
  }

  toggle(featureName) {
    if (this.flags[featureName]) {
      this.flags[featureName].enabled = !this.flags[featureName].enabled;
    }
  }

  getEnabledFeatures(userRole = null) {
    return Object.entries(this.flags)
      .filter(([name, feature]) => this.isEnabled(name, userRole))
      .map(([name, feature]) => ({
        name,
        description: feature.description
      }));
  }

  getFeatureStatus(featureName) {
    const feature = this.flags[featureName];
    if (!feature) return null;

    return {
      name: featureName,
      enabled: feature.enabled,
      description: feature.description,
      missingRequirements: this.getMissingRequirements(feature)
    };
  }

  getMissingRequirements(feature) {
    const missing = [];
    
    if (feature.requires) {
      for (const req of feature.requires) {
        if (req.startsWith('ENV:')) {
          const envVar = req.replace('ENV:', '');
          if (!process.env[envVar]) {
            missing.push(envVar);
          }
        } else if (!this.isEnabled(req)) {
          missing.push(req);
        }
      }
    }

    return missing;
  }

  getStatus() {
    const features = Object.keys(this.flags);
    const enabled = features.filter(f => this.isEnabled(f));
    
    return {
      total: features.length,
      enabled: enabled.length,
      disabled: features.length - enabled.length,
      environment: this.environment
    };
  }
}

module.exports = { FeatureFlags, FEATURE_FLAGS };
