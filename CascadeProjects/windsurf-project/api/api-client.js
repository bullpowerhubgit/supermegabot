/**
 * Robuster API Client mit Retry-Logik, Fehlerbehandlung, Logging
 * Unterstuetzt alle externen APIs des SuperMegaBot Systems
 */

import { secureConfig } from '../bots/shared/secure-config.js';
import { UnifiedLogger } from '../bots/shared/unified-logger.js';

const logger = new UnifiedLogger({ name: 'api-client', consoleOutput: false });

export class APIClient {
  constructor(serviceName, options = {}) {
    this.service = serviceName;
    this.config = secureConfig.getApiConfig(serviceName);
    this.baseUrl = options.baseUrl || this.config.baseUrl;
    this.apiKey = options.apiKey || this.config.apiKey;
    this.timeout = options.timeout || 10000;
    this.maxRetries = options.maxRetries || 3;
    this.retryDelay = options.retryDelay || 1000;
    this.headers = options.headers || {};
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    const requestOptions = {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiKey}`,
        ...this.headers,
        ...(options.headers || {})
      }
    };

    if (options.body && typeof options.body === 'object') {
      requestOptions.body = JSON.stringify(options.body);
    }

    let lastError;
    for (let attempt = 1; attempt <= this.maxRetries; attempt++) {
      try {
        const start = Date.now();
        const response = await fetch(url, requestOptions);
        const responseTime = Date.now() - start;
        clearTimeout(timeoutId);

        if (!response.ok) {
          const errorBody = await response.text().catch(() => '');
          throw new Error(`HTTP ${response.status}: ${errorBody.slice(0, 200)}`);
        }

        const data = await response.json().catch(() => ({}));
        logger.info(`${this.service} request succeeded`, { endpoint, attempt, responseTime });
        return { success: true, data, responseTime, attempt };
      } catch (err) {
        lastError = err;
        clearTimeout(timeoutId);
        if (attempt < this.maxRetries) {
          logger.warn(`${this.service} request failed, retrying`, { endpoint, attempt, error: err.message });
          await new Promise(r => setTimeout(r, this.retryDelay * attempt));
        }
      }
    }

    logger.error(`${this.service} request failed after ${this.maxRetries} retries`, { endpoint, error: lastError.message });
    return { success: false, error: lastError.message, attempts: this.maxRetries };
  }

  async get(endpoint, options = {}) {
    return this.request(endpoint, { ...options, method: 'GET' });
  }

  async post(endpoint, body, options = {}) {
    return this.request(endpoint, { ...options, method: 'POST', body });
  }

  async put(endpoint, body, options = {}) {
    return this.request(endpoint, { ...options, method: 'PUT', body });
  }

  async delete(endpoint, options = {}) {
    return this.request(endpoint, { ...options, method: 'DELETE' });
  }
}

export async function healthCheckAll() {
  const services = ['anthropic', 'openai', 'perplexity', 'shopify'];
  const results = {};
  for (const svc of services) {
    const client = new APIClient(svc);
    try {
      const res = await client.get('/health').catch(() => ({ success: false }));
      results[svc] = res.success ? 'healthy' : 'unreachable';
    } catch {
      results[svc] = 'error';
    }
  }
  return results;
}
