import { IntercomConfig, IntercomAction } from './types.js';
import axios from 'axios';

export class IntercomController {
  private config: IntercomConfig;
  private baseUrl = 'https://api.intercom.io';

  constructor(config: IntercomConfig) {
    this.config = config;
  }

  async execute(action: IntercomAction): Promise<any> {
    switch (action.action) {
      case 'getConversations':
        return this.getConversations();
      case 'getConversation':
        return this.getConversation(action.conversationId!);
      case 'sendMessage':
        return this.sendMessage(action.data);
      case 'getContacts':
        return this.getContacts();
      case 'getContact':
        return this.getContact(action.contactId!);
      case 'createContact':
        return this.createContact(action.data);
      default:
        throw new Error(`Unknown Intercom action: ${action.action}`);
    }
  }

  private async getConversations(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/conversations`, {
        headers: {
          Authorization: `Bearer ${this.config.accessToken}`,
          Accept: 'application/json',
        },
      });
      return { success: true, conversations: response.data.conversations };
    } catch (error: any) {
      throw new Error(`Intercom getConversations failed: ${error.message}`);
    }
  }

  private async getConversation(conversationId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/conversations/${conversationId}`, {
        headers: {
          Authorization: `Bearer ${this.config.accessToken}`,
          Accept: 'application/json',
        },
      });
      return { success: true, conversation: response.data };
    } catch (error: any) {
      throw new Error(`Intercom getConversation failed: ${error.message}`);
    }
  }

  private async sendMessage(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/messages`, data, {
        headers: {
          Authorization: `Bearer ${this.config.accessToken}`,
          Accept: 'application/json',
        },
      });
      return { success: true, message: response.data };
    } catch (error: any) {
      throw new Error(`Intercom sendMessage failed: ${error.message}`);
    }
  }

  private async getContacts(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/contacts`, {
        headers: {
          Authorization: `Bearer ${this.config.accessToken}`,
          Accept: 'application/json',
        },
      });
      return { success: true, contacts: response.data.contacts };
    } catch (error: any) {
      throw new Error(`Intercom getContacts failed: ${error.message}`);
    }
  }

  private async getContact(contactId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/contacts/${contactId}`, {
        headers: {
          Authorization: `Bearer ${this.config.accessToken}`,
          Accept: 'application/json',
        },
      });
      return { success: true, contact: response.data };
    } catch (error: any) {
      throw new Error(`Intercom getContact failed: ${error.message}`);
    }
  }

  private async createContact(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/contacts`, data, {
        headers: {
          Authorization: `Bearer ${this.config.accessToken}`,
          Accept: 'application/json',
        },
      });
      return { success: true, contact: response.data };
    } catch (error: any) {
      throw new Error(`Intercom createContact failed: ${error.message}`);
    }
  }
}
