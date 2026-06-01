/**
 * Unified API Client for All Systems
 * Supports: Anthropic, OpenAI, Fiverr, Upwork, Etsy, Shopify, Printful, AliExpress
 */

class ApiClient {
  constructor(configPath = './api-config.json') {
    this.config = this.loadConfig(configPath);
    this.cache = new Map();
    this.rateLimits = new Map();
  }

  loadConfig(configPath) {
    try {
      const fs = require('fs');
      if (fs.existsSync(configPath)) {
        return JSON.parse(fs.readFileSync(configPath, 'utf8'));
      }
    } catch (error) {
      console.warn('Could not load API config:', error.message);
    }
    return {};
  }

  saveConfig(configPath = './api-config.json') {
    try {
      const fs = require('fs');
      fs.writeFileSync(configPath, JSON.stringify(this.config, null, 2));
    } catch (error) {
      console.error('Could not save API config:', error.message);
    }
  }

  checkRateLimit(apiName) {
    const now = Date.now();
    const limit = this.rateLimits.get(apiName);
    if (limit && now < limit.resetTime) {
      return { allowed: false, waitTime: limit.resetTime - now };
    }
    return { allowed: true };
  }

  setRateLimit(apiName, resetTime) {
    this.rateLimits.set(apiName, { resetTime });
  }

  async request(apiName, endpoint, options = {}) {
    const { allowed, waitTime } = this.checkRateLimit(apiName);
    if (!allowed) {
      throw new Error(`Rate limit exceeded for ${apiName}. Wait ${waitTime}ms`);
    }

    const apiConfig = this.config[apiName];
    if (!apiConfig || !apiConfig.apiKey) {
      throw new Error(`API key not configured for ${apiName}`);
    }

    const url = `${apiConfig.baseUrl}${endpoint}`;
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers
    };

    // Add authentication based on API
    if (apiName === 'anthropic') {
      headers['x-api-key'] = apiConfig.apiKey;
      headers['anthropic-version'] = apiConfig.version || '2023-06-01';
    } else if (apiName === 'openai') {
      headers['Authorization'] = `Bearer ${apiConfig.apiKey}`;
    } else if (apiName === 'etsy' || apiName === 'shopify') {
      headers['Authorization'] = `Bearer ${apiConfig.apiKey}`;
    } else {
      headers['Authorization'] = `Bearer ${apiConfig.apiKey}`;
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers,
        body: options.body ? JSON.stringify(options.body) : undefined
      });

      if (!response.ok) {
        const error = await response.text();
        throw new Error(`API Error ${response.status}: ${error}`);
      }

      const data = await response.json();
      
      // Set rate limit if headers present
      const resetTime = response.headers.get('x-ratelimit-reset');
      if (resetTime) {
        this.setRateLimit(apiName, parseInt(resetTime) * 1000);
      }

      return data;
    } catch (error) {
      console.error(`API request failed for ${apiName}:`, error.message);
      throw error;
    }
  }

  // Anthropic/Claude API
  async claude(messages, options = {}) {
    return this.request('anthropic', '/messages', {
      method: 'POST',
      body: {
        model: options.model || this.config.anthropic?.model || 'claude-sonnet-4-5',
        max_tokens: options.maxTokens || 4096,
        messages: messages
      }
    });
  }

  // OpenAI API
  async openai(messages, options = {}) {
    return this.request('openai', '/chat/completions', {
      method: 'POST',
      body: {
        model: options.model || this.config.openai?.model || 'gpt-4o',
        messages: messages,
        max_tokens: options.maxTokens || 4096
      }
    });
  }

  // Fiverr API
  async fiverrGigs(query, options = {}) {
    return this.request('fiverr', '/gigs', {
      method: 'GET',
      body: {
        query: query,
        limit: options.limit || 10
      }
    });
  }

  // Upwork API
  async upworkJobs(query, options = {}) {
    return this.request('upwork', '/jobs/v2/search/jobs', {
      method: 'GET',
      body: {
        q: query,
        limit: options.limit || 10
      }
    });
  }

  // Etsy API
  async etsyListings(keyword, options = {}) {
    return this.request('etsy', '/listings/active', {
      method: 'GET',
      body: {
        keywords: keyword,
        limit: options.limit || 25
      }
    });
  }

  // Shopify API
  async shopifyProducts(options = {}) {
    const storeUrl = this.config.shopify?.storeUrl;
    if (!storeUrl) throw new Error('Shopify store URL not configured');
    
    return this.request('shopify', '/products.json', {
      method: 'GET',
      body: {
        limit: options.limit || 50
      }
    });
  }

  // Printful API
  async printfulProducts(options = {}) {
    return this.request('printful', '/store/products', {
      method: 'GET',
      body: {}
    });
  }

  // AliExpress API
  async aliexpressProducts(keyword, options = {}) {
    return this.request('aliexpress', '/products/search', {
      method: 'GET',
      body: {
        keyword: keyword,
        pageSize: options.pageSize || 20
      }
    });
  }
}

// Export for Node.js
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ApiClient;
}

// Export for browser
if (typeof window !== 'undefined') {
  window.ApiClient = ApiClient;
}
