import { PayPalConfig, PayPalAction } from './types.js';
import axios from 'axios';

export class PayPalController {
  private config: PayPalConfig;
  private baseUrl: string;
  private accessToken?: string;

  constructor(config: PayPalConfig) {
    this.config = config;
    this.baseUrl = config.mode === 'live' 
      ? 'https://api-m.paypal.com' 
      : 'https://api-m.sandbox.paypal.com';
  }

  private async authenticate(): Promise<void> {
    if (this.accessToken) return;

    try {
      const auth = Buffer.from(`${this.config.clientId}:${this.config.clientSecret}`).toString('base64');
      const response = await axios.post(`${this.baseUrl}/v1/oauth2/token`, 'grant_type=client_credentials', {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'Authorization': `Basic ${auth}`,
        },
      });
      this.accessToken = response.data.access_token;
    } catch (error: any) {
      throw new Error(`PayPal authentication failed: ${error.message}`);
    }
  }

  async execute(action: PayPalAction): Promise<any> {
    await this.authenticate();

    switch (action.action) {
      case 'createOrder':
        return this.createOrder(action.data);
      case 'captureOrder':
        return this.captureOrder(action.orderId!);
      case 'getOrder':
        return this.getOrder(action.orderId!);
      case 'createPayment':
        return this.createPayment(action.data);
      case 'executePayment':
        return this.executePayment(action.paymentId!, action.data);
      case 'getPayment':
        return this.getPayment(action.paymentId!);
      default:
        throw new Error(`Unknown PayPal action: ${action.action}`);
    }
  }

  private async createOrder(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/v2/checkout/orders`, data, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, order: response.data };
    } catch (error: any) {
      throw new Error(`PayPal createOrder failed: ${error.message}`);
    }
  }

  private async captureOrder(orderId: string): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/v2/checkout/orders/${orderId}/capture`, {}, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, order: response.data };
    } catch (error: any) {
      throw new Error(`PayPal captureOrder failed: ${error.message}`);
    }
  }

  private async getOrder(orderId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/v2/checkout/orders/${orderId}`, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, order: response.data };
    } catch (error: any) {
      throw new Error(`PayPal getOrder failed: ${error.message}`);
    }
  }

  private async createPayment(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/v1/payments/payment`, data, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, payment: response.data };
    } catch (error: any) {
      throw new Error(`PayPal createPayment failed: ${error.message}`);
    }
  }

  private async executePayment(paymentId: string, data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/v1/payments/payment/${paymentId}/execute`, data, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, payment: response.data };
    } catch (error: any) {
      throw new Error(`PayPal executePayment failed: ${error.message}`);
    }
  }

  private async getPayment(paymentId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/v1/payments/payment/${paymentId}`, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, payment: response.data };
    } catch (error: any) {
      throw new Error(`PayPal getPayment failed: ${error.message}`);
    }
  }
}
