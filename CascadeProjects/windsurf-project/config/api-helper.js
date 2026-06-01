/**
 * API Integration Helper für SuperMegaBot Tools
 * Ermöglicht jedem Tool einfachen Zugriff auf zentrale API-Konfiguration
 */

import centralConfig from './central-api-config.js';
import fs from 'fs';
import path from 'path';

class APIHelper {
  constructor(toolName = 'unknown-tool') {
    this.toolName = toolName;
    this.central = centralConfig;
    this.cache = new Map();
    this.lastCacheUpdate = null;
  }

  /**
   * Prüft ob eine API verfügbar ist
   */
  isAPIAvailable(service) {
    try {
      return this.central.isAPIAvailable(service);
    } catch (error) {
      console.warn(`⚠️  API-Check fehlgeschlagen für ${service}:`, error.message);
      return false;
    }
  }

  /**
   * Gibt API-Konfiguration zurück mit Caching
   */
  getAPIConfig(service, useCache = true) {
    const cacheKey = `${service}_config`;
    
    if (useCache && this.cache.has(cacheKey)) {
      const cached = this.cache.get(cacheKey);
      if (Date.now() - cached.timestamp < 300000) { // 5 Minuten Cache
        return cached.data;
      }
    }

    try {
      const config = this.central.getExternalAPI(service);
      if (config) {
        // Cache aktualisieren
        this.cache.set(cacheKey, {
          data: config,
          timestamp: Date.now()
        });
        return config;
      }
    } catch (error) {
      console.warn(`⚠️  Konfiguration nicht gefunden für ${service}:`, error.message);
    }

    return null;
  }

  /**
   * Erstellt HTTP-Client für eine API
   */
  createAPIClient(service, customOptions = {}) {
    const config = this.getAPIConfig(service);
    if (!config) {
      throw new Error(`API-Konfiguration für ${service} nicht verfügbar`);
    }

    const defaultOptions = {
      baseURL: config.baseUrl,
      headers: {
        'Authorization': `Bearer ${config.apiKey}`,
        'Content-Type': 'application/json',
        'User-Agent': `${this.toolName}/1.0.0`
      },
      timeout: 30000,
      retries: 3
    };

    return {
      ...defaultOptions,
      ...customOptions,
      service,
      config,
      isAvailable: () => this.isAPIAvailable(service)
    };
  }

  /**
   * Gibt alle verfügbaren APIs zurück
   */
  getAvailableAPIs() {
    try {
      return {
        gcp: this.central.getEnabledGCPApis(),
        external: Object.keys(this.central.config.external || {}),
        total: this.central.getEnabledGCPApis().length + Object.keys(this.central.config.external || {}).length
      };
    } catch (error) {
      console.warn('⚠️  API-Liste konnte nicht geladen werden:', error.message);
      return { gcp: [], external: [], total: 0 };
    }
  }

  /**
   * Prüft ob alle benötigten APIs für ein Tool verfügbar sind
   */
  checkRequiredAPIs(requiredAPIs = []) {
    const results = {
      available: [],
      missing: [],
      total: requiredAPIs.length
    };

    requiredAPIs.forEach(api => {
      if (this.isAPIAvailable(api)) {
        results.available.push(api);
      } else {
        results.missing.push(api);
      }
    });

    results.ready = results.missing.length === 0;
    results.percentage = Math.round((results.available.length / results.total) * 100);

    return results;
  }

  /**
   * Loggt API-Nutzung für Monitoring
   */
  logAPIUsage(service, operation, success = true, error = null) {
    const logEntry = {
      timestamp: new Date().toISOString(),
      tool: this.toolName,
      service,
      operation,
      success,
      error: error ? error.message : null
    };

    // In Production: Logging Service oder Datei
    console.log(`🔗 API Usage: ${this.toolName} → ${service} → ${operation} (${success ? '✅' : '❌'})`);
    
    if (!success && error) {
      console.error(`   Error: ${error.message}`);
    }

    return logEntry;
  }

  /**
   * Führt API-Aufruf mit automatischem Retry und Logging aus
   */
  async executeAPI(service, operation, apiCall, options = {}) {
    const { retries = 3, timeout = 30000 } = options;
    let lastError = null;

    // API-Verfügbarkeit prüfen
    if (!this.isAPIAvailable(service)) {
      const error = new Error(`API ${service} ist nicht verfügbar`);
      this.logAPIUsage(service, operation, false, error);
      throw error;
    }

    // Retry-Logik
    for (let attempt = 1; attempt <= retries; attempt++) {
      try {
        const startTime = Date.now();
        const result = await Promise.race([
          apiCall(),
          new Promise((_, reject) => 
            setTimeout(() => reject(new Error('Timeout')), timeout)
          )
        ]);
        
        const duration = Date.now() - startTime;
        this.logAPIUsage(service, operation, true);
        
        return {
          success: true,
          data: result,
          duration,
          attempts: attempt
        };
        
      } catch (error) {
        lastError = error;
        console.warn(`🔄 API Retry ${attempt}/${retries} für ${service}:`, error.message);
        
        if (attempt < retries) {
          // Exponential Backoff
          await new Promise(resolve => setTimeout(resolve, Math.pow(2, attempt) * 1000));
        }
      }
    }

    // Alle Retries fehlgeschlagen
    this.logAPIUsage(service, operation, false, lastError);
    throw lastError;
  }

  /**
   * Gibt Projekt-Informationen zurück
   */
  getProjectInfo() {
    try {
      return {
        projectId: this.central.getProjectId(),
        authMethod: this.central.getAuthMethod(),
        billing: this.central.getBillingInfo()
      };
    } catch (error) {
      console.warn('⚠️  Projekt-Info konnte nicht geladen werden:', error.message);
      return null;
    }
  }

  /**
   * Erstellt API-Helper für ein spezifisches Tool
   */
  static forTool(toolName) {
    return new APIHelper(toolName);
  }

  /**
   * Gibt System-Status zurück
   */
  getSystemStatus() {
    try {
      const status = this.central.getStatus();
      const apis = this.getAvailableAPIs();
      
      return {
        tool: this.toolName,
        system: {
          loaded: status.loaded,
          lastUpdated: status.lastUpdated,
          projectId: status.projectId
        },
        apis: apis,
        cache: {
          entries: this.cache.size,
          lastUpdate: this.lastCacheUpdate
        }
      };
    } catch (error) {
      return {
        tool: this.toolName,
        error: error.message,
        status: 'error'
      };
    }
  }

  /**
   * Cache leeren
   */
  clearCache() {
    this.cache.clear();
    this.lastCacheUpdate = Date.now();
  }
}

// Export für verschiedene Verwendungszwecke
export {
  APIHelper,
  
  // Quick-Access Funktionen
  createHelper as default,
  createHelper,
  isAvailable,
  getConfig,
  createClient,
  
  // Batch-Operationen
  checkAPIs,
  executeCall
};

function createHelper(toolName) {
  return new APIHelper(toolName);
}

function isAvailable(service) {
  return new APIHelper().isAPIAvailable(service);
}

function getConfig(service) {
  return new APIHelper().getAPIConfig(service);
}

function createClient(service, toolName) {
  return new APIHelper(toolName).createAPIClient(service);
}

function checkAPIs(requiredAPIs, toolName) {
  return new APIHelper(toolName).checkRequiredAPIs(requiredAPIs);
}

function executeCall(service, operation, apiCall, toolName) {
  return new APIHelper(toolName).executeAPI(service, operation, apiCall);
}
