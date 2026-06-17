import { KlaviyoConfig, KlaviyoAction } from './types.js';
import axios from 'axios';

export class KlaviyoController {
  private config: KlaviyoConfig;
  private baseUrl = 'https://a.klaviyo.com/api';

  constructor(config: KlaviyoConfig) {
    this.config = config;
  }

  async execute(action: KlaviyoAction): Promise<any> {
    switch (action.action) {
      case 'getLists':
        return this.getLists();
      case 'getList':
        return this.getList(action.listId!);
      case 'createList':
        return this.createList(action.data);
      case 'getMembers':
        return this.getMembers(action.listId!);
      case 'addMember':
        return this.addMember(action.listId!, action.data);
      case 'sendEmail':
        return this.sendEmail(action.data);
      case 'getCampaigns':
        return this.getCampaigns();
      default:
        throw new Error(`Unknown Klaviyo action: ${action.action}`);
    }
  }

  private async getLists(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/lists`, {
        headers: { Authorization: `Klaviyo-API-Key ${this.config.apiKey}` },
      });
      return { success: true, lists: response.data.data };
    } catch (error: any) {
      throw new Error(`Klaviyo getLists failed: ${error.message}`);
    }
  }

  private async getList(listId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/lists/${listId}`, {
        headers: { Authorization: `Klaviyo-API-Key ${this.config.apiKey}` },
      });
      return { success: true, list: response.data.data };
    } catch (error: any) {
      throw new Error(`Klaviyo getList failed: ${error.message}`);
    }
  }

  private async createList(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/lists`, { data }, {
        headers: { Authorization: `Klaviyo-API-Key ${this.config.apiKey}` },
      });
      return { success: true, list: response.data.data };
    } catch (error: any) {
      throw new Error(`Klaviyo createList failed: ${error.message}`);
    }
  }

  private async getMembers(listId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/lists/${listId}/members`, {
        headers: { Authorization: `Klaviyo-API-Key ${this.config.apiKey}` },
      });
      return { success: true, members: response.data.data };
    } catch (error: any) {
      throw new Error(`Klaviyo getMembers failed: ${error.message}`);
    }
  }

  private async addMember(listId: string, data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/lists/${listId}/members`, { data }, {
        headers: { Authorization: `Klaviyo-API-Key ${this.config.apiKey}` },
      });
      return { success: true, member: response.data.data };
    } catch (error: any) {
      throw new Error(`Klaviyo addMember failed: ${error.message}`);
    }
  }

  private async sendEmail(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/campaigns/send`, { data }, {
        headers: { Authorization: `Klaviyo-API-Key ${this.config.apiKey}` },
      });
      return { success: true, result: response.data };
    } catch (error: any) {
      throw new Error(`Klaviyo sendEmail failed: ${error.message}`);
    }
  }

  private async getCampaigns(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/campaigns`, {
        headers: { Authorization: `Klaviyo-API-Key ${this.config.apiKey}` },
      });
      return { success: true, campaigns: response.data.data };
    } catch (error: any) {
      throw new Error(`Klaviyo getCampaigns failed: ${error.message}`);
    }
  }
}
