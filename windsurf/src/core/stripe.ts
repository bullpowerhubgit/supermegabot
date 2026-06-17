import { StripeConfig, StripeAction } from './types.js';
import Stripe from 'stripe';

export class StripeController {
  private config: StripeConfig;
  private stripe: Stripe;

  constructor(config: StripeConfig) {
    this.config = config;
    this.stripe = new Stripe(config.apiKey, {
      apiVersion: (config.apiVersion || '2024-06-20') as any,
    });
  }

  async execute(action: StripeAction): Promise<any> {
    switch (action.action) {
      case 'createPaymentIntent':
        return this.createPaymentIntent(action.data);
      case 'confirmPayment':
        return this.confirmPayment(action.data);
      case 'createCustomer':
        return this.createCustomer(action.data);
      case 'getCustomer':
        return this.getCustomer(action.id!);
      case 'createSubscription':
        return this.createSubscription(action.data);
      case 'cancelSubscription':
        return this.cancelSubscription(action.id!);
      case 'getSubscription':
        return this.getSubscription(action.id!);
      case 'createInvoice':
        return this.createInvoice(action.data);
      case 'getInvoice':
        return this.getInvoice(action.id!);
      case 'listInvoices':
        return this.listInvoices(action.data);
      default:
        throw new Error(`Unknown Stripe action: ${action.action}`);
    }
  }

  private async createPaymentIntent(data: any): Promise<any> {
    try {
      const paymentIntent = await this.stripe.paymentIntents.create(data);
      return { success: true, paymentIntent };
    } catch (error: any) {
      throw new Error(`Payment intent creation failed: ${error.message}`);
    }
  }

  private async confirmPayment(data: any): Promise<any> {
    try {
      const paymentIntent = await this.stripe.paymentIntents.confirm(data.paymentIntentId, data);
      return { success: true, paymentIntent };
    } catch (error: any) {
      throw new Error(`Payment confirmation failed: ${error.message}`);
    }
  }

  private async createCustomer(data: any): Promise<any> {
    try {
      const customer = await this.stripe.customers.create(data);
      return { success: true, customer };
    } catch (error: any) {
      throw new Error(`Customer creation failed: ${error.message}`);
    }
  }

  private async getCustomer(id: string): Promise<any> {
    try {
      const customer = await this.stripe.customers.retrieve(id);
      return { success: true, customer };
    } catch (error: any) {
      throw new Error(`Customer retrieval failed: ${error.message}`);
    }
  }

  private async createSubscription(data: any): Promise<any> {
    try {
      const subscription = await this.stripe.subscriptions.create(data);
      return { success: true, subscription };
    } catch (error: any) {
      throw new Error(`Subscription creation failed: ${error.message}`);
    }
  }

  private async cancelSubscription(id: string): Promise<any> {
    try {
      const subscription = await this.stripe.subscriptions.cancel(id);
      return { success: true, subscription };
    } catch (error: any) {
      throw new Error(`Subscription cancellation failed: ${error.message}`);
    }
  }

  private async getSubscription(id: string): Promise<any> {
    try {
      const subscription = await this.stripe.subscriptions.retrieve(id);
      return { success: true, subscription };
    } catch (error: any) {
      throw new Error(`Subscription retrieval failed: ${error.message}`);
    }
  }

  private async createInvoice(data: any): Promise<any> {
    try {
      const invoice = await this.stripe.invoices.create(data);
      return { success: true, invoice };
    } catch (error: any) {
      throw new Error(`Invoice creation failed: ${error.message}`);
    }
  }

  private async getInvoice(id: string): Promise<any> {
    try {
      const invoice = await this.stripe.invoices.retrieve(id);
      return { success: true, invoice };
    } catch (error: any) {
      throw new Error(`Invoice retrieval failed: ${error.message}`);
    }
  }

  private async listInvoices(data: any): Promise<any> {
    try {
      const invoices = await this.stripe.invoices.list(data);
      return { success: true, invoices };
    } catch (error: any) {
      throw new Error(`Invoice listing failed: ${error.message}`);
    }
  }
}
