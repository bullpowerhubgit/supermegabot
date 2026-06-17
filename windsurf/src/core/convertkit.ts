import { ConvertKitConfig, ConvertKitAction } from './types.js';
import axios from 'axios';

export class ConvertKitController {
  private config: ConvertKitConfig;
  private baseUrl = 'https://api.convertkit.com/v3';

  constructor(config: ConvertKitConfig) {
    this.config = config;
  }

  async execute(action: ConvertKitAction): Promise<any> {
    switch (action.action) {
      case 'getSubscribers':
        return this.getSubscribers();
      case 'getSubscriber':
        return this.getSubscriber(action.subscriberId!);
      case 'addSubscriber':
        return this.addSubscriber(action.data);
      case 'getForms':
        return this.getForms();
      case 'getCampaigns':
        return this.getCampaigns();
      default:
        throw new Error(`Unknown ConvertKit action: ${action.action}`);
    }
  }

  private async getSubscribers(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/subscribers`, {
        params: { api_secret: this.config.apiKey },
      });
      return { success: true, subscribers: response.data.subscribers };
    } catch (error: any) {
      throw new Error(`ConvertKit getSubscribers failed: ${error.message}`);
    }
  }

  private async getSubscriber(subscriberId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/subscribers/${subscriberId}`, {
        params: { api_secret: this.config.apiKey },
      });
      return { success: true, subscriber: response.data.subscriber };
    } catch (error: any) {
      throw new Error(`ConvertKit getSubscriber failed: ${error.message}`);
    }
  }

  private async addSubscriber(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/forms/${data.formId}/subscribe`, data, {
        params: { api_secret: this.config.apiKey },
      });
      return { success: true, subscriber: response.data.subscriber };
    } catch (error: any) {
      throw new Error(`ConvertKit addSubscriber failed: ${error.message}`);
    }
  }

  private async getForms(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/forms`, {
        params: { api_secret: this.config.apiKey },
      });
      return { success: true, forms: response.data.forms };
    } catch (error: any) {
      throw new Error(`ConvertKit getForms failed: ${error.message}`);
    }
  }

  private async getCampaigns(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/campaigns`, {
        params: { api_secret: this.config.apiKey },
      });
      return { success: true, campaigns: response.data.campaigns };
    } catch (error: any) {
      throw new Error(`ConvertKit getCampaigns failed: ${error.message}`);
    }
  }
}
