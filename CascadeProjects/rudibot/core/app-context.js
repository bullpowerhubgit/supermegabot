/**
 * App Context - Shared Services Registry
 * Zentraler Kontext für alle Module mit API-Clients, Helpers und Services
 */

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

class AppContext {
  constructor(options = {}) {
    this.logger = options.logger || console;
    this.env = process.env;
    
    // Service Registry
    this.services = new Map();
    
    // API Clients
    this.clients = new Map();
    
    // Helpers
    this.helpers = new Map();
    
    // Cache
    this.cache = new Map();
    
    this.initializeServices();
    this.initializeClients();
    this.initializeHelpers();
  }

  initializeServices() {
    // Shopify Service
    this.services.set('shopify', {
      storeUrl: this.env.SHOPIFY_STORE_URL,
      apiVersion: this.env.SHOPIFY_API_VERSION || '2025-01',
      adminToken: this.env.SHOPIFY_ADMIN_TOKEN,
      
      async fetch(endpoint, opts = {}) {
        const url = `https://${this.storeUrl}/admin/api/${this.apiVersion}/${endpoint}`;
        const res = await fetch(url, {
          ...opts,
          headers: {
            'X-Shopify-Access-Token': this.adminToken,
            'Content-Type': 'application/json',
            ...(opts.headers || {})
          }
        });
        
        if (!res.ok) {
          throw new Error(`Shopify API ${res.status}: ${await res.text()}`);
        }
        
        return res.json();
      },
      
      async getOrders(params = {}) {
        const query = new URLSearchParams(params).toString();
        return this.fetch(`orders.json?${query}`);
      },
      
      async getProducts(params = {}) {
        const query = new URLSearchParams(params).toString();
        return this.fetch(`products.json?${query}`);
      },
      
      async createRefund(orderId, refund) {
        return this.fetch(`orders/${orderId}/refunds.json`, {
          method: 'POST',
          body: JSON.stringify({ refund })
        });
      }
    });

    // Printify Service
    this.services.set('printify', {
      apiKey: this.env.PRINTIFY_API_KEY,
      shopId: this.env.PRINTIFY_SHOP_ID,
      baseUrl: 'https://api.printify.com/v1',
      
      async fetch(endpoint, opts = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const res = await fetch(url, {
          ...opts,
          headers: {
            'Authorization': `Bearer ${this.apiKey}`,
            'Content-Type': 'application/json',
            ...(opts.headers || {})
          }
        });
        
        if (!res.ok) {
          throw new Error(`Printify API ${res.status}: ${await res.text()}`);
        }
        
        return res.json();
      },
      
      async getOrders() {
        return this.fetch(`/shops/${this.shopId}/orders.json`);
      },
      
      async getProducts() {
        return this.fetch(`/shops/${this.shopId}/products.json`);
      }
    });

    // PayPal Service
    this.services.set('paypal', {
      clientId: this.env.PAYPAL_CLIENT_ID,
      clientSecret: this.env.PAYPAL_CLIENT_SECRET,
      sandbox: this.env.PAYPAL_SANDBOX === 'true',
      baseUrl: this.env.PAYPAL_SANDBOX === 'true' 
        ? 'https://api-m.sandbox.paypal.com'
        : 'https://api-m.paypal.com',
      
      async getAccessToken() {
        const auth = Buffer.from(`${this.clientId}:${this.clientSecret}`).toString('base64');
        const res = await fetch(`${this.baseUrl}/v1/oauth2/token`, {
          method: 'POST',
          headers: {
            'Authorization': `Basic ${auth}`,
            'Content-Type': 'application/x-www-form-urlencoded'
          },
          body: 'grant_type=client_credentials'
        });
        
        if (!res.ok) {
          throw new Error(`PayPal Auth ${res.status}: ${await res.text()}`);
        }
        
        const data = await res.json();
        return data.access_token;
      },
      
      async fetch(endpoint, opts = {}) {
        const token = await this.getAccessToken();
        const url = `${this.baseUrl}${endpoint}`;
        const res = await fetch(url, {
          ...opts,
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
            ...(opts.headers || {})
          }
        });
        
        if (!res.ok) {
          throw new Error(`PayPal API ${res.status}: ${await res.text()}`);
        }
        
        return res.json();
      },
      
      async getTransactions(startDate, endDate) {
        const query = new URLSearchParams({
          start_date: startDate.toISOString(),
          end_date: endDate.toISOString()
        }).toString();
        return this.fetch(`/v1/reporting/transactions?${query}`);
      }
    });

    // Bank Service
    this.services.set('bank', {
      importPath: this.env.BANK_IMPORT_PATH || './imports/bank',
      
      async importCSV(filename) {
        const filePath = path.join(this.importPath, filename);
        
        if (!fs.existsSync(filePath)) {
          throw new Error(`Bank CSV nicht gefunden: ${filePath}`);
        }
        
        const content = fs.readFileSync(filePath, 'utf-8');
        return this.parseBankCSV(content);
      },
      
      parseBankCSV(content) {
        // TODO: Implementieren mit echtem Bank-CSV-Parser
        const lines = content.split('\n').filter(line => line.trim());
        const transactions = [];
        
        for (let i = 1; i < lines.length; i++) { // Skip header
          const cols = lines[i].split(';');
          if (cols.length >= 5) {
            transactions.push({
              date: cols[0],
              description: cols[1],
              amount: parseFloat(cols[2].replace(',', '.')),
              balance: parseFloat(cols[3].replace(',', '.')),
              iban: cols[4]
            });
          }
        }
        
        return transactions;
      }
    });

    // ELSTER Service
    this.services.set('elster', {
      testMode: this.env.ELSTER_TEST_MODE !== 'false',
      
      async submitDeclaration(xml, period, options = {}) {
        // TODO: Implementieren mit echtem ELSTER-Client
        return {
          id: `ELSTER_${Date.now()}`,
          status: 'submitted',
          confirmation: 'TEST_MODE_CONFIRMATION',
          testMode: this.testMode || options.testMode
        };
      },
      
      generateXML(vatData) {
        // TODO: Implementieren mit echtem ELSTER-XML-Generator
        return `<?xml version="1.0" encoding="UTF-8"?>
<ELSTER>
  <Period>${vatData.period}</Period>
  <VAT>${vatData.totalVAT}</VAT>
</ELSTER>`;
      }
    });

    // Security Service
    this.services.set('security', {
      apiKeys: new Map(),
      
      registerAPIKey(name, config) {
        this.apiKeys.set(name, {
          name,
          type: config.type,
          endpoint: config.endpoint,
          lastValidated: null,
          validationErrors: [],
          rotationRequired: false
        });
      },
      
      async validateAPIKey(name, key) {
        const config = this.apiKeys.get(name);
        if (!config) {
          throw new Error(`API Key nicht registriert: ${name}`);
        }
        
        try {
          // TODO: Implementieren mit echtem API-Validation
          const response = await fetch(config.endpoint, {
            headers: { 'Authorization': `Bearer ${key}` }
          });
          
          config.lastValidated = new Date();
          config.validationErrors = [];
          
          return response.ok;
        } catch (error) {
          config.validationErrors.push(error.message);
          return false;
        }
      },
      
      async rotateKey(name, newKey) {
        const config = this.apiKeys.get(name);
        if (!config) {
          throw new Error(`API Key nicht registriert: ${name}`);
        }
        
        // TODO: Implementieren mit echtem Key-Rotation
        config.rotationRequired = false;
        config.lastRotated = new Date();
        
        return true;
      },
      
      async revokeKey(name) {
        const config = this.apiKeys.get(name);
        if (!config) {
          throw new Error(`API Key nicht registriert: ${name}`);
        }
        
        // TODO: Implementieren mit echtem Key-Revocation
        this.apiKeys.delete(name);
        return true;
      },
      
      async deepScan() {
        const results = {
          timestamp: new Date(),
          findings: [],
          vulnerabilities: [],
          recommendations: []
        };
        
        // TODO: Implementieren mit echtem Deep-Scan
        for (const [name, config] of this.apiKeys) {
          if (config.validationErrors.length > 0) {
            results.vulnerabilities.push({
              type: 'api_key_error',
              service: name,
              errors: config.validationErrors
            });
          }
        }
        
        return results;
      }
    });

    // Notification Service
    this.services.set('notification', {
      telegram: {
        botToken: this.env.TELEGRAM_BOT_TOKEN,
        chatId: this.env.TELEGRAM_CHAT_ID,
        
        async sendMessage(message) {
          if (!this.botToken || !this.chatId) {
            console.warn('Telegram Bot nicht konfiguriert');
            return false;
          }
          
          const url = `https://api.telegram.org/bot${this.botToken}/sendMessage`;
          const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              chat_id: this.chatId,
              text: message,
              parse_mode: 'HTML'
            })
          });
          
          return res.ok;
        }
      },
      
      email: {
        provider: this.env.EMAIL_PROVIDER || 'resend',
        apiKey: this.env.RESEND_API_KEY,
        from: this.env.EMAIL_FROM,
        
        async send(to, subject, content) {
          if (!this.apiKey) {
            console.warn('Email Service nicht konfiguriert');
            return false;
          }
          
          // TODO: Implementieren mit echtem Email-Service
          console.log(`Email gesendet an ${to}: ${subject}`);
          return true;
        }
      }
    });

    this.logger.info('🔧 App Context Services initialisiert');
  }

  initializeClients() {
    // HTTP Client mit Retry Logic
    this.clients.set('http', {
      async fetchWithRetry(url, opts = {}, retries = 3) {
        for (let i = 0; i < retries; i++) {
          try {
            const res = await fetch(url, opts);
            if (res.ok) return res;
            
            if (i === retries - 1) {
              throw new Error(`HTTP ${res.status} nach ${retries} Versuchen`);
            }
            
            // Exponential Backoff
            await new Promise(resolve => setTimeout(resolve, Math.pow(2, i) * 1000));
          } catch (error) {
            if (i === retries - 1) throw error;
            await new Promise(resolve => setTimeout(resolve, Math.pow(2, i) * 1000));
          }
        }
      }
    });

    // Database Client (Platzhalter)
    this.clients.set('database', {
      async query(sql, params = []) {
        // TODO: Implementieren mit echtem Database-Client
        return { rows: [], rowCount: 0 };
      },
      
      async transaction(callback) {
        // TODO: Implementieren mit echten Transactions
        return callback(this);
      }
    });

    this.logger.info('🌐 App Context Clients initialisiert');
  }

  initializeHelpers() {
    // Date Helper
    this.helpers.set('date', {
      getCurrentTaxPeriod() {
        const now = new Date();
        const year = now.getFullYear();
        const month = String(now.getMonth() + 1).padStart(2, '0');
        return `${year}${month}`;
      },
      
      getQuarterStart(date = new Date()) {
        const quarter = Math.floor(date.getMonth() / 3);
        return new Date(date.getFullYear(), quarter * 3, 1);
      },
      
      getQuarterEnd(date = new Date()) {
        const quarter = Math.floor(date.getMonth() / 3);
        return new Date(date.getFullYear(), quarter * 3 + 3, 0);
      },
      
      addDays(date, days) {
        const result = new Date(date);
        result.setDate(result.getDate() + days);
        return result;
      },
      
      formatGerman(date) {
        return date.toLocaleDateString('de-DE');
      }
    });

    // Currency Helper
    this.helpers.set('currency', {
      formatEUR(amount) {
        return new Intl.NumberFormat('de-DE', {
          style: 'currency',
          currency: 'EUR'
        }).format(amount);
      },
      
      parseEUR(string) {
        const clean = string.replace(/[€\s]/g, '').replace(',', '.');
        return parseFloat(clean);
      },
      
      calculateVAT(amount, rate = 19) {
        return {
          net: amount / (1 + rate / 100),
          vat: amount - (amount / (1 + rate / 100)),
          gross: amount
        };
      }
    });

    // Validation Helper
    this.helpers.set('validation', {
      isValidEmail(email) {
        const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return regex.test(email);
      },
      
      isValidIBAN(iban) {
        const regex = /^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$/;
        return regex.test(iban.replace(/\s/g, ''));
      },
      
      isValidURL(url) {
        try {
          new URL(url);
          return true;
        } catch {
          return false;
        }
      },
      
      sanitizeString(str) {
        return str.trim().replace(/[<>]/g, '');
      }
    });

    // Encryption Helper
    this.helpers.set('encryption', {
      generateKey() {
        return crypto.randomBytes(32).toString('hex');
      },
      
      encrypt(text, key) {
        const iv = crypto.randomBytes(16);
        const cipher = crypto.createCipher('aes-256-cbc', key);
        let encrypted = cipher.update(text, 'utf8', 'hex');
        encrypted += cipher.final('hex');
        return { iv: iv.toString('hex'), encrypted };
      },
      
      decrypt(encryptedData, key) {
        const decipher = crypto.createDecipher('aes-256-cbc', key);
        let decrypted = decipher.update(encryptedData.encrypted, 'hex', 'utf8');
        decrypted += decipher.final('utf8');
        return decrypted;
      },
      
      hash(text) {
        return crypto.createHash('sha256').update(text).digest('hex');
      }
    });

    // File Helper
    this.helpers.set('file', {
      async ensureDir(dirPath) {
        if (!fs.existsSync(dirPath)) {
          fs.mkdirSync(dirPath, { recursive: true });
        }
      },
      
      async readFile(filePath) {
        if (!fs.existsSync(filePath)) {
          throw new Error(`Datei nicht gefunden: ${filePath}`);
        }
        return fs.readFileSync(filePath, 'utf-8');
      },
      
      async writeFile(filePath, content) {
        await this.helpers.get('file').ensureDir(path.dirname(filePath));
        fs.writeFileSync(filePath, content, 'utf-8');
      },
      
      async appendFile(filePath, content) {
        await this.helpers.get('file').ensureDir(path.dirname(filePath));
        fs.appendFileSync(filePath, content, 'utf-8');
      }
    });

    this.logger.info('🛠️ App Context Helpers initialisiert');
  }

  // Service Access Methods
  getService(name) {
    const service = this.services.get(name);
    if (!service) {
      throw new Error(`Service nicht gefunden: ${name}`);
    }
    return service;
  }

  getClient(name) {
    const client = this.clients.get(name);
    if (!client) {
      throw new Error(`Client nicht gefunden: ${name}`);
    }
    return client;
  }

  getHelper(name) {
    const helper = this.helpers.get(name);
    if (!helper) {
      throw new Error(`Helper nicht gefunden: ${name}`);
    }
    return helper;
  }

  // Cache Methods
  setCache(key, value, ttl = 3600000) { // 1 hour default
    this.cache.set(key, {
      value,
      expires: Date.now() + ttl
    });
  }

  getCache(key) {
    const cached = this.cache.get(key);
    if (!cached) return null;
    
    if (Date.now() > cached.expires) {
      this.cache.delete(key);
      return null;
    }
    
    return cached.value;
  }

  clearCache() {
    this.cache.clear();
  }

  // Health Check
  async healthCheck() {
    const results = {
      timestamp: new Date(),
      services: {},
      clients: {},
      overall: 'healthy'
    };

    // Check Services
    for (const [name, service] of this.services) {
      try {
        if (service.healthCheck) {
          results.services[name] = await service.healthCheck();
        } else {
          results.services[name] = { status: 'ok', message: 'No health check' };
        }
      } catch (error) {
        results.services[name] = { status: 'error', message: error.message };
        results.overall = 'degraded';
      }
    }

    // Check Clients
    for (const [name, client] of this.clients) {
      try {
        if (client.healthCheck) {
          results.clients[name] = await client.healthCheck();
        } else {
          results.clients[name] = { status: 'ok', message: 'No health check' };
        }
      } catch (error) {
        results.clients[name] = { status: 'error', message: error.message };
        results.overall = 'degraded';
      }
    }

    return results;
  }

  // Cleanup
  async cleanup() {
    this.clearCache();
    
    // Cleanup services
    for (const [name, service] of this.services) {
      if (service.cleanup) {
        try {
          await service.cleanup();
        } catch (error) {
          this.logger.error(`Cleanup Fehler für Service ${name}:`, error);
        }
      }
    }
    
    this.logger.info('🧹 App Context aufgeräumt');
  }
}

module.exports = { AppContext };
