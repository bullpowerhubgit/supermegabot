import { PipedriveConfig, PipedriveAction } from './types.js';
import axios from 'axios';

export class PipedriveController {
  private config: PipedriveConfig;
  private baseUrl: string;

  constructor(config: PipedriveConfig) {
    this.config = config;
    this.baseUrl = `https://${config.companyDomain}.pipedrive.com/api/v1`;
  }

  async execute(action: PipedriveAction): Promise<any> {
    switch (action.action) {
      case 'getDeals':
        return this.getDeals();
      case 'getDeal':
        return this.getDeal(action.dealId!);
      case 'createDeal':
        return this.createDeal(action.data);
      case 'updateDeal':
        return this.updateDeal(action.dealId!, action.data);
      case 'deleteDeal':
        return this.deleteDeal(action.dealId!);
      case 'getContacts':
        return this.getContacts();
      case 'getContact':
        return this.getContact(action.contactId!);
      case 'createContact':
        return this.createContact(action.data);
      default:
        throw new Error(`Unknown Pipedrive action: ${action.action}`);
    }
  }

  private async getDeals(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/deals`, {
        params: { api_token: this.config.apiToken },
      });
      return { success: true, deals: response.data.data };
    } catch (error: any) {
      throw new Error(`Pipedrive getDeals failed: ${error.message}`);
    }
  }

  private async getDeal(dealId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/deals/${dealId}`, {
        params: { api_token: this.config.apiToken },
      });
      return { success: true, deal: response.data.data };
    } catch (error: any) {
      throw new Error(`Pipedrive getDeal failed: ${error.message}`);
    }
  }

  private async createDeal(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/deals`, data, {
        params: { api_token: this.config.apiToken },
      });
      return { success: true, deal: response.data.data };
    } catch (error: any) {
      throw new Error(`Pipedrive createDeal failed: ${error.message}`);
    }
  }

  private async updateDeal(dealId: string, data: any): Promise<any> {
    try {
      const response = await axios.put(`${this.baseUrl}/deals/${dealId}`, data, {
        params: { api_token: this.config.apiToken },
      });
      return { success: true, deal: response.data.data };
    } catch (error: any) {
      throw new Error(`Pipedrive updateDeal failed: ${error.message}`);
    }
  }

  private async deleteDeal(dealId: string): Promise<any> {
    try {
      await axios.delete(`${this.baseUrl}/deals/${dealId}`, {
        params: { api_token: this.config.apiToken },
      });
      return { success: true, message: 'Deal deleted' };
    } catch (error: any) {
      throw new Error(`Pipedrive deleteDeal failed: ${error.message}`);
    }
  }

  private async getContacts(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/persons`, {
        params: { api_token: this.config.apiToken },
      });
      return { success: true, contacts: response.data.data };
    } catch (error: any) {
      throw new Error(`Pipedrive getContacts failed: ${error.message}`);
    }
  }

  private async getContact(contactId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/persons/${contactId}`, {
        params: { api_token: this.config.apiToken },
      });
      return { success: true, contact: response.data.data };
    } catch (error: any) {
      throw new Error(`Pipedrive getContact failed: ${error.message}`);
    }
  }

  private async createContact(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/persons`, data, {
        params: { api_token: this.config.apiToken },
      });
      return { success: true, contact: response.data.data };
    } catch (error: any) {
      throw new Error(`Pipedrive createContact failed: ${error.message}`);
    }
  }
}
