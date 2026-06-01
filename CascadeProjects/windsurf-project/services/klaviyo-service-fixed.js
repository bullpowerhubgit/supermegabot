/**
 * Klaviyo Service with Centralized Retry Logic
 * Handles email marketing automation with proper queue management
 */

import axios from 'axios';
import { EventEmitter } from 'events';

class KlaviyoService extends EventEmitter {
  constructor(config = {}) {
    super();
    this.apiKey = config.apiKey || process.env.KLAVIYO_API_KEY || 'mock_private_key';
    this.publicKey = config.publicKey || process.env.KLAVIYO_PUBLIC_KEY || 'mock_public_key';
    this.baseURL = 'https://a.klaviyo.com/api';
    this.timeout = config.timeout || 30000;
    this.maxRetries = config.maxRetries || 3;
    this.retryDelay = config.retryDelay || 1000;
    
    // Queue management
    this.queue = [];
    this.isProcessing = false;
    this.maxQueueSize = config.maxQueueSize || 1000;
    
    // Rate limiting
    this.rateLimit = {
      requests: 0,
      windowMs: 60000, // 1 minute
      maxRequests: 1000, // Klaviyo's rate limit
      resetTime: Date.now() + 60000
    };
    
    // Initialize axios instance
    this.client = axios.create({
      baseURL: this.baseURL,
      timeout: this.timeout,
      headers: {
        'Authorization': `Klaviyo-API-Key ${this.apiKey}`,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'revision': '2023-10-15'
      }
    });
    
    // Request interceptor for rate limiting
    this.client.interceptors.request.use(
      (config) => this.checkRateLimit(config),
      (error) => Promise.reject(error)
    );
    
    // Response interceptor for rate limit headers
    this.client.interceptors.response.use(
      (response) => this.handleRateLimitHeaders(response),
      (error) => this.handleRequestError(error)
    );

    if (this.apiKey === 'mock_private_key') {
      console.log('[Klaviyo] Running in mock mode - no real API calls will be made');
    }
  }
  
  /**
   * Check rate limit before making request
   */
  checkRateLimit(config) {
    const now = Date.now();
    
    // Reset window if needed
    if (now >= this.rateLimit.resetTime) {
      this.rateLimit.requests = 0;
      this.rateLimit.resetTime = now + this.rateLimit.windowMs;
    }
    
    // Check if we're at the limit
    if (this.rateLimit.requests >= this.rateLimit.maxRequests) {
      const waitTime = this.rateLimit.resetTime - now;
      throw new Error(`Rate limit exceeded. Wait ${waitTime}ms`);
    }
    
    this.rateLimit.requests++;
    return config;
  }
  
  /**
   * Handle rate limit headers from response
   */
  handleRateLimitHeaders(response) {
    const rateLimitRemaining = response.headers['x-klaviyo-rate-limit-remaining'];
    const rateLimitReset = response.headers['x-klaviyo-rate-limit-reset'];
    
    if (rateLimitRemaining !== undefined) {
      this.rateLimit.requests = this.rateLimit.maxRequests - parseInt(rateLimitRemaining);
    }
    
    if (rateLimitReset) {
      this.rateLimit.resetTime = parseInt(rateLimitReset) * 1000;
    }
    
    return response;
  }
  
  /**
   * Handle request errors with retry logic
   */
  async handleRequestError(error) {
    const config = error.config;
    
    // Don't retry if we've already retried too many times
    if (config.__retryCount >= this.maxRetries) {
      this.emit('error', {
        error: error.message,
        url: config.url,
        method: config.method,
        retries: config.__retryCount,
        failed: true
      });
      return Promise.reject(error);
    }
    
    // Don't retry on certain status codes
    if (error.response && [400, 401, 403, 404, 422].includes(error.response.status)) {
      return Promise.reject(error);
    }
    
    // Increment retry count
    config.__retryCount = config.__retryCount || 0;
    config.__retryCount++;
    
    // Calculate delay with exponential backoff
    const delay = this.retryDelay * Math.pow(2, config.__retryCount - 1);
    
    this.emit('retry', {
      error: error.message,
      url: config.url,
      method: config.method,
      attempt: config.__retryCount,
      delay
    });
    
    // Wait and retry
    await new Promise(resolve => setTimeout(resolve, delay));
    
    return this.client(config);
  }
  
  /**
   * Add request to queue
   */
  async queueRequest(requestData) {
    if (this.queue.length >= this.maxQueueSize) {
      throw new Error('Queue is full. Cannot add more requests.');
    }
    
    const queueItem = {
      id: this.generateQueueId(),
      ...requestData,
      timestamp: Date.now(),
      attempts: 0
    };
    
    this.queue.push(queueItem);
    this.emit('queued', queueItem);
    
    // Start processing if not already running
    if (!this.isProcessing) {
      this.processQueue();
    }
    
    return queueItem.id;
  }
  
  /**
   * Process queue
   */
  async processQueue() {
    if (this.isProcessing || this.queue.length === 0) {
      return;
    }
    
    this.isProcessing = true;
    this.emit('queueProcessing', { queueLength: this.queue.length });
    
    while (this.queue.length > 0) {
      const item = this.queue.shift();
      
      try {
        await this.executeRequest(item);
        this.emit('processed', item);
      } catch (error) {
        item.attempts++;
        
        if (item.attempts < this.maxRetries) {
          // Re-queue for retry
          this.queue.unshift(item);
          this.emit('retryQueued', item);
          
          // Wait before retry
          await new Promise(resolve => setTimeout(resolve, this.retryDelay * item.attempts));
        } else {
          // Max retries reached, discard
          this.emit('failed', { item, error: error.message });
        }
      }
    }
    
    this.isProcessing = false;
    this.emit('queueProcessed');
  }
  
  /**
   * Execute queued request
   */
  async executeRequest(item) {
    const { method, endpoint, data, headers } = item;
    
    const config = {
      method: method.toLowerCase(),
      url: endpoint,
      data,
      headers: { ...headers }
    };
    
    const response = await this.client(config);
    return response.data;
  }
  
  /**
   * Create/update profile
   */
  async createOrUpdateProfile(profileData, options = {}) {
    const requestData = {
      method: 'POST',
      endpoint: '/profiles/',
      data: {
        data: {
          type: 'profile',
          attributes: profileData
        }
      }
    };
    
    if (options.queue) {
      return await this.queueRequest(requestData);
    }
    
    try {
      const response = await this.client.post('/profiles/', {
        data: {
          type: 'profile',
          attributes: profileData
        }
      });
      return response.data;
    } catch (error) {
      this.emit('error', { operation: 'createOrUpdateProfile', error: error.message });
      throw error;
    }
  }
  
  /**
   * Track event
   */
  async trackEvent(eventName, profileId, properties, options = {}) {
    const requestData = {
      method: 'POST',
      endpoint: '/events/',
      data: {
        data: {
          type: 'event',
          attributes: {
            metric: {
              data: {
                type: 'metric',
                attributes: {
                  name: eventName
                }
              }
            },
            profile: {
              data: {
                type: 'profile',
                id: profileId
              }
            },
            properties: properties,
            time: options.timestamp || new Date().toISOString()
          }
        }
      }
    };
    
    if (options.queue) {
      return await this.queueRequest(requestData);
    }
    
    try {
      const response = await this.client.post('/events/', requestData.data);
      return response.data;
    } catch (error) {
      this.emit('error', { operation: 'trackEvent', error: error.message });
      throw error;
    }
  }
  
  /**
   * Get queue status
   */
  getQueueStatus() {
    return {
      length: this.queue.length,
      isProcessing: this.isProcessing,
      rateLimit: {
        requests: this.rateLimit.requests,
        maxRequests: this.rateLimit.maxRequests,
        resetTime: new Date(this.rateLimit.resetTime)
      },
      mockMode: this.apiKey === 'mock_private_key'
    };
  }
  
  /**
   * Generate queue ID
   */
  generateQueueId() {
    return `klv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }
  
  /**
   * Health check
   */
  async healthCheck() {
    try {
      const response = await this.client.get('/metrics/');
      return {
        status: 'healthy',
        klaviyoConnected: true,
        queueStatus: this.getQueueStatus(),
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      return {
        status: 'unhealthy',
        klaviyoConnected: false,
        error: error.message,
        timestamp: new Date().toISOString()
      };
    }
  }
}

// Singleton instance
let klaviyoService = null;

function getKlaviyoService(config) {
  if (!klaviyoService) {
    klaviyoService = new KlaviyoService(config);
  }
  return klaviyoService;
}

export {
  KlaviyoService,
  getKlaviyoService
};
