/**
 * Google Analytics 4 Service with Queue Management
 * Handles GA4 event tracking with proper queue and retry logic
 */

import axios from 'axios';
import { EventEmitter } from 'events';

class AnalyticsService extends EventEmitter {
  constructor(config = {}) {
    super();
    this.measurementId = config.measurementId || process.env.GOOGLE_ANALYTICS_MEASUREMENT_ID || 'G-XXXXXXXXXX';
    this.apiSecret = config.apiSecret || process.env.GOOGLE_ANALYTICS_API_SECRET || 'mock_secret';
    this.baseURL = `https://www.google-analytics.com/mp/collect`;
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
      maxRequests: 100, // GA4 rate limit
      resetTime: Date.now() + 60000
    };
    
    // Initialize axios instance
    this.client = axios.create({
      baseURL: this.baseURL,
      timeout: this.timeout,
      headers: {
        'Content-Type': 'application/json'
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

    if (this.apiSecret === 'mock_secret') {
      console.log('[Analytics] Running in mock mode - no real GA4 calls will be made');
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
    // GA4 doesn't provide rate limit headers, so we'll use our internal tracking
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
   * Track purchase event with proper type casting
   */
  async trackPurchase(purchaseData) {
    try {
      // Validate items structure with proper type handling
      const validatedItems = purchaseData.items.map(item => ({
        item_id: String(item.item_id),
        item_name: String(item.item_name),
        category: item.category ? String(item.category) : undefined,
        quantity: typeof item.quantity === 'number' ? item.quantity : Number(item.quantity) || 1,
        price: typeof item.price === 'number' ? item.price : Number(item.price) || 0,
        item_variant: item.item_variant ? String(item.item_variant) : undefined,
        item_brand: item.item_brand ? String(item.item_brand) : undefined,
      }));

      const event = {
        name: 'purchase',
        params: {
          transaction_id: purchaseData.transaction_id,
          value: typeof purchaseData.value === 'number' ? purchaseData.value : Number(purchaseData.value) || 0,
          currency: String(purchaseData.currency),
          items: validatedItems,
          coupon: purchaseData.coupon ? String(purchaseData.coupon) : undefined,
          shipping: typeof purchaseData.shipping === 'number' ? purchaseData.shipping : (purchaseData.shipping ? Number(purchaseData.shipping) : undefined),
          tax: typeof purchaseData.tax === 'number' ? purchaseData.tax : (purchaseData.tax ? Number(purchaseData.tax) : undefined),
        },
      };

      return await this.sendEvent(event);
    } catch (error) {
      console.error('[Analytics] Purchase tracking error:', error);
      return {
        queued: false,
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }
  
  /**
   * Send event to GA4
   */
  async sendEvent(event, options = {}) {
    const requestData = {
      method: 'POST',
      endpoint: `?measurement_id=${this.measurementId}&api_secret=${this.apiSecret}`,
      data: {
        client_id: event.clientId || 'anonymous',
        user_id: event.userId,
        events: [{
          name: event.name,
          params: event.params
        }]
      }
    };
    
    if (options.queue) {
      return await this.queueRequest(requestData);
    }
    
    try {
      // Mock mode for development/testing
      if (this.apiSecret === 'mock_secret') {
        console.log('[Analytics] Mock mode - would send event:', event.name);
        return {
          queued: false,
          success: true,
          eventId: this.generateEventId()
        };
      }

      const response = await this.client.post('', requestData.data);
      return {
        queued: false,
        success: true,
        eventId: this.generateEventId()
      };
    } catch (error) {
      console.error('[Analytics] Event sending error:', error);
      return {
        queued: false,
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }
  
  /**
   * Track custom event
   */
  async trackEvent(eventName, params = {}, options = {}) {
    const event = {
      name: eventName,
      params: params
    };
    
    return await this.sendEvent(event, options);
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
      mockMode: this.apiSecret === 'mock_secret'
    };
  }
  
  /**
   * Generate event ID
   */
  generateEventId() {
    return `ga4_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }
  
  /**
   * Generate queue ID
   */
  generateQueueId() {
    return `queue_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }
  
  /**
   * Health check
   */
  async healthCheck() {
    try {
      const testEvent = await this.trackEvent('health_check', { test: true });
      return {
        status: 'healthy',
        ga4Connected: this.apiSecret !== 'mock_secret',
        queueStatus: this.getQueueStatus(),
        testEventSuccess: testEvent.success,
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      return {
        status: 'unhealthy',
        ga4Connected: false,
        error: error.message,
        timestamp: new Date().toISOString()
      };
    }
  }
}

// Singleton instance
let analyticsService = null;

function getAnalyticsService(config) {
  if (!analyticsService) {
    analyticsService = new AnalyticsService(config);
  }
  return analyticsService;
}

export {
  AnalyticsService,
  getAnalyticsService
};
