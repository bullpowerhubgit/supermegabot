/**
 * Zentrale API-Konfiguration für SuperMegaBot System
 * Lädt und kombiniert alle API-Konfigurationen aus verschiedenen Quellen
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

class CentralAPIConfig {
  constructor() {
    this.config = {
      gcp: null,
      external: {},
      loaded: false,
      lastUpdated: null
    };
    this.configPath = {
      gcp: path.join(__dirname, '../RudiBot-Secure-API/gcp-config.json'),
      external: path.join(__dirname, '../api-config.json'),
      agent: path.join(__dirname, '../agent-configs.json')
    };
  }

  /**
   * Lädt alle Konfigurationen
   */
  loadAllConfigs() {
    try {
      // GCP Konfiguration laden
      if (fs.existsSync(this.configPath.gcp)) {
        this.config.gcp = JSON.parse(fs.readFileSync(this.configPath.gcp, 'utf8'));
        console.log('✅ GCP Konfiguration geladen');
      }

      // Externe API Konfiguration laden
      if (fs.existsSync(this.configPath.external)) {
        const externalConfig = JSON.parse(fs.readFileSync(this.configPath.external, 'utf8'));
        this.config.external = externalConfig;
        console.log('✅ Externe API Konfiguration geladen');
      }

      // Agent Konfiguration laden
      if (fs.existsSync(this.configPath.agent)) {
        this.config.agent = JSON.parse(fs.readFileSync(this.configPath.agent, 'utf8'));
        console.log('✅ Agent Konfiguration geladen');
      }

      this.config.loaded = true;
      this.config.lastUpdated = new Date().toISOString();
      
      console.log(`🔧 Zentrale API-Konfiguration aktualisiert: ${this.config.lastUpdated}`);
      return this.config;

    } catch (error) {
      console.error('❌ Fehler beim Laden der Konfiguration:', error.message);
      throw error;
    }
  }

  /**
   * Gibt GCP Projekt-ID zurück
   */
  getProjectId() {
    if (!this.config.loaded) this.loadAllConfigs();
    return this.config.gcp?.project?.id || this.config.external?.gcp?.projectId;
  }

  /**
   * Gibt alle aktivierten GCP APIs zurück
   */
  getEnabledGCPApis() {
    if (!this.config.loaded) this.loadAllConfigs();
    
    // Aus RudiBot-Secure-API Konfiguration
    if (this.config.gcp?.apis?.enabled) {
      return this.config.gcp.apis.enabled.map(api => api.name);
    }
    
    // Aus api-config.json
    if (this.config.external?.gcp?.apis?.enabled) {
      return this.config.external.gcp.apis.enabled;
    }
    
    return [];
  }

  /**
   * Gibt externe API Konfiguration zurück
   */
  getExternalAPI(service) {
    if (!this.config.loaded) this.loadAllConfigs();
    return this.config.external[service];
  }

  /**
   * Prüft ob eine API verfügbar ist
   */
  isAPIAvailable(service) {
    if (!this.config.loaded) this.loadAllConfigs();
    
    // GCP APIs
    if (service.includes('.googleapis.com')) {
      return this.getEnabledGCPApis().includes(service);
    }
    
    // Externe APIs
    return this.config.external.hasOwnProperty(service);
  }

  /**
   * Gibt Billing-Informationen zurück
   */
  getBillingInfo() {
    if (!this.config.loaded) this.loadAllConfigs();
    
    return {
      account: this.config.gcp?.project?.billing_account || this.config.external?.gcp?.billingAccount,
      accountName: this.config.gcp?.project?.billing_account_name || 'Mein Rechnungskonto',
      requiredApis: this.config.gcp?.apis?.billing_required || this.config.external?.gcp?.apis?.billingRequired || []
    };
  }

  /**
   * Gibt GenAI Konfiguration zurück
   */
  getGenAIConfig() {
    if (!this.config.loaded) this.loadAllConfigs();
    
    return {
      projectId: this.getProjectId(),
      region: this.config.external?.genai?.region || 'us-central1',
      model: this.config.external?.genai?.model || 'gemini-1.5-pro',
      temperature: this.config.external?.genai?.temperature || 0.7,
      maxTokens: this.config.external?.genai?.maxTokens || 1024,
      enabled: this.config.external?.genai?.enabled || false,
      apiKey: this.config.external?.genai?.apiKey || process.env.GOOGLE_AI_API_KEY
    };
  }

  /**
   * Prüft ob GenAI verfügbar ist
   */
  isGenAIAvailable() {
    const genaiConfig = this.getGenAIConfig();
    return genaiConfig.enabled && genaiConfig.projectId && genaiConfig.apiKey;
  }

  /**
   * Erstellt GenAI Client Konfiguration
   */
  createGenAIClientConfig() {
    const genaiConfig = this.getGenAIConfig();
    
    if (!this.isGenAIAvailable()) {
      throw new Error('GenAI nicht konfiguriert oder nicht verfügbar');
    }

    return {
      projectId: genaiConfig.projectId,
      region: genaiConfig.region,
      model: genaiConfig.model,
      temperature: genaiConfig.temperature,
      maxTokens: genaiConfig.maxTokens,
      apiKey: genaiConfig.apiKey,
      baseURL: `https://${genaiConfig.region}-aiplatform.googleapis.com/v1/projects/${genaiConfig.projectId}/locations/${genaiConfig.region}/publishers/google/models/${genaiConfig.model}:generateContent`
    };
  }

  /**
   * Gibt Auth-Methode zurück
   */
  getAuthMethod() {
    if (!this.config.loaded) this.loadAllConfigs();
    return this.config.gcp?.auth?.method || this.config.external?.gcp?.authMethod || 'gcloud';
  }

  /**
   * Erstellt API Client Konfiguration
   */
  createClientConfig(service) {
    const config = this.getExternalAPI(service);
    if (!config) {
      throw new Error(`API Konfiguration für ${service} nicht gefunden`);
    }

    return {
      baseUrl: config.baseUrl,
      headers: {
        'Authorization': `Bearer ${config.apiKey}`,
        'Content-Type': 'application/json'
      },
      timeout: 30000,
      retries: 3
    };
  }

  /**
   * Validiert Konfiguration
   */
  validateConfig() {
    const errors = [];
    
    if (!this.config.loaded) {
      errors.push('Konfiguration nicht geladen');
    }

    if (!this.getProjectId()) {
      errors.push('Keine GCP Projekt-ID gefunden');
    }

    if (this.getEnabledGCPApis().length === 0) {
      errors.push('Keine GCP APIs aktiviert');
    }

    return {
      valid: errors.length === 0,
      errors
    };
  }

  /**
   * Gibt Konfigurations-Status zurück
   */
  getStatus() {
    if (!this.config.loaded) this.loadAllConfigs();
    
    return {
      loaded: this.config.loaded,
      lastUpdated: this.config.lastUpdated,
      projectId: this.getProjectId(),
      enabledApis: this.getEnabledGCPApis().length,
      externalApis: Object.keys(this.config.external).length,
      authMethod: this.getAuthMethod(),
      billing: this.getBillingInfo()
    };
  }
}

// Singleton Instanz
const centralConfig = new CentralAPIConfig();

// Automatisch laden beim ersten Import
centralConfig.loadAllConfigs();

export default centralConfig;
