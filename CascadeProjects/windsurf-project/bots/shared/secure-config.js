import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import dotenv from 'dotenv';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, '../../');

export class SecureConfig {
  constructor() {
    this.config = {};
    this.loaded = false;
    this.loadEnv();
  }

  loadEnv() {
    const envFiles = ['.env', '.env.local', '.env.platform', '.env.quickcash'];
    for (const file of envFiles) {
      const fp = path.join(PROJECT_ROOT, file);
      if (fs.existsSync(fp)) {
        dotenv.config({ path: fp });
      }
    }
  }

  get(key, fallback = null) {
    return process.env[key] ?? fallback;
  }

  getRequired(key) {
    const val = process.env[key];
    if (!val) throw new Error(`Required env var ${key} is missing`);
    return val;
  }

  getApiConfig(service) {
    const prefix = service.toUpperCase().replace(/-/g, '_');
    return {
      apiKey: this.get(`${prefix}_API_KEY`) || this.get(`${service}_apiKey`),
      baseUrl: this.get(`${prefix}_BASE_URL`) || this.get(`${service}_baseUrl`),
      secretKey: this.get(`${prefix}_SECRET_KEY`) || this.get(`${service}_secretKey`),
      enabled: this.get(`${prefix}_ENABLED`, 'false') === 'true'
    };
  }

  getAll() {
    const apis = [
      'anthropic', 'openai', 'perplexity', 'shopify', 'etsy',
      'fiverr', 'upwork', 'printful', 'stripe', 'sendgrid',
      'gcp', 'aliexpress'
    ];
    const result = {};
    for (const api of apis) {
      result[api] = this.getApiConfig(api);
    }
    return result;
  }

  validate() {
    const critical = ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY'];
    const missing = critical.filter(k => !this.get(k));
    const apis = this.getAll();
    const activeApis = Object.entries(apis).filter(([_, v]) => v.apiKey).map(([k]) => k);
    return { valid: missing.length === 0, missing, activeApis, totalApis: Object.keys(apis).length };
  }
}

export const secureConfig = new SecureConfig();
