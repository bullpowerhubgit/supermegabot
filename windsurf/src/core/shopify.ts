import { ShopifyConfig, ShopifyAction } from './types.js';

export class ShopifyController {
  private config: ShopifyConfig;
  private baseUrl: string;

  constructor(config: ShopifyConfig) {
    this.config = config;
    const apiVersion = config.apiVersion || '2024-01';
    this.baseUrl = `https://${config.shopDomain}/admin/api/${apiVersion}`;
  }

  private async request(endpoint: string, method: string = 'GET', body?: any): Promise<any> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers: HeadersInit = {
      'X-Shopify-Access-Token': this.config.accessToken,
      'Content-Type': 'application/json',
    };

    const options: RequestInit = {
      method,
      headers,
    };

    if (body && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
      options.body = JSON.stringify(body);
    }

    const response = await fetch(url, options);
    
    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Shopify API error: ${response.status} - ${error}`);
    }

    return response.json();
  }

  async execute(action: ShopifyAction): Promise<any> {
    switch (action.action) {
      case 'getProducts':
        return this.getProducts(action.query);
      case 'getProduct':
        return this.getProduct(action.id!);
      case 'createProduct':
        return this.createProduct(action.data);
      case 'updateProduct':
        return this.updateProduct(action.id!, action.data);
      case 'deleteProduct':
        return this.deleteProduct(action.id!);
      case 'getOrders':
        return this.getOrders(action.query);
      case 'getOrder':
        return this.getOrder(action.id!);
      case 'createOrder':
        return this.createOrder(action.data);
      case 'updateOrder':
        return this.updateOrder(action.id!, action.data);
      case 'getCustomers':
        return this.getCustomers(action.query);
      case 'getCustomer':
        return this.getCustomer(action.id!);
      case 'createCustomer':
        return this.createCustomer(action.data);
      case 'updateCustomer':
        return this.updateCustomer(action.id!, action.data);
      case 'getInventory':
        return this.getInventory(action.query);
      case 'updateInventory':
        return this.updateInventory(action.data);
      case 'createWebhook':
        return this.createWebhook(action.data);
      case 'deleteWebhook':
        return this.deleteWebhook(action.id!);
      case 'getWebhooks':
        return this.getWebhooks();
      default:
        throw new Error(`Unknown Shopify action: ${action.action}`);
    }
  }

  private async getProducts(query?: any): Promise<any> {
    const params = new URLSearchParams(query || {}).toString();
    return this.request(`/products.json?${params}`);
  }

  private async getProduct(id: string): Promise<any> {
    return this.request(`/products/${id}.json`);
  }

  private async createProduct(data: any): Promise<any> {
    return this.request('/products.json', 'POST', { product: data });
  }

  private async updateProduct(id: string, data: any): Promise<any> {
    return this.request(`/products/${id}.json`, 'PUT', { product: data });
  }

  private async deleteProduct(id: string): Promise<any> {
    return this.request(`/products/${id}.json`, 'DELETE');
  }

  private async getOrders(query?: any): Promise<any> {
    const params = new URLSearchParams(query || {}).toString();
    return this.request(`/orders.json?${params}`);
  }

  private async getOrder(id: string): Promise<any> {
    return this.request(`/orders/${id}.json`);
  }

  private async createOrder(data: any): Promise<any> {
    return this.request('/orders.json', 'POST', { order: data });
  }

  private async updateOrder(id: string, data: any): Promise<any> {
    return this.request(`/orders/${id}.json`, 'PUT', { order: data });
  }

  private async getCustomers(query?: any): Promise<any> {
    const params = new URLSearchParams(query || {}).toString();
    return this.request(`/customers.json?${params}`);
  }

  private async getCustomer(id: string): Promise<any> {
    return this.request(`/customers/${id}.json`);
  }

  private async createCustomer(data: any): Promise<any> {
    return this.request('/customers.json', 'POST', { customer: data });
  }

  private async updateCustomer(id: string, data: any): Promise<any> {
    return this.request(`/customers/${id}.json`, 'PUT', { customer: data });
  }

  private async getInventory(query?: any): Promise<any> {
    const params = new URLSearchParams(query || {}).toString();
    return this.request(`/inventory_levels.json?${params}`);
  }

  private async updateInventory(data: any): Promise<any> {
    return this.request('/inventory_levels/adjust.json', 'POST', {
      location_id: data.location_id,
      inventory_item_id: data.inventory_item_id,
      available_adjustment: data.available_adjustment,
    });
  }

  private async createWebhook(data: any): Promise<any> {
    return this.request('/webhooks.json', 'POST', { webhook: data });
  }

  private async deleteWebhook(id: string): Promise<any> {
    return this.request(`/webhooks/${id}.json`, 'DELETE');
  }

  private async getWebhooks(): Promise<any> {
    return this.request('/webhooks.json');
  }
}
