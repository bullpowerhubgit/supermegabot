import { HelpScoutConfig, HelpScoutAction } from './types.js';
import axios from 'axios';

export class HelpScoutController {
  private config: HelpScoutConfig;
  private baseUrl = 'https://api.helpscout.net/v2';

  constructor(config: HelpScoutConfig) {
    this.config = config;
  }

  async execute(action: HelpScoutAction): Promise<any> {
    switch (action.action) {
      case 'getConversations':
        return this.getConversations();
      case 'getConversation':
        return this.getConversation(action.conversationId!);
      case 'createConversation':
        return this.createConversation(action.data);
      case 'getMailboxes':
        return this.getMailboxes();
      case 'getCustomers':
        return this.getCustomers();
      default:
        throw new Error(`Unknown HelpScout action: ${action.action}`);
    }
  }

  private async getConversations(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/conversations`, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, conversations: response.data._embedded.conversations };
    } catch (error: any) {
      throw new Error(`HelpScout getConversations failed: ${error.message}`);
    }
  }

  private async getConversation(conversationId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/conversations/${conversationId}`, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, conversation: response.data };
    } catch (error: any) {
      throw new Error(`HelpScout getConversation failed: ${error.message}`);
    }
  }

  private async createConversation(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/conversations`, data, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, conversation: response.data };
    } catch (error: any) {
      throw new Error(`HelpScout createConversation failed: ${error.message}`);
    }
  }

  private async getMailboxes(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/mailboxes`, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, mailboxes: response.data._embedded.mailboxes };
    } catch (error: any) {
      throw new Error(`HelpScout getMailboxes failed: ${error.message}`);
    }
  }

  private async getCustomers(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/customers`, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, customers: response.data._embedded.customers };
    } catch (error: any) {
      throw new Error(`HelpScout getCustomers failed: ${error.message}`);
    }
  }
}
