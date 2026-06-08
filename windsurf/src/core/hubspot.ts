import { HubSpotConfig, HubSpotAction } from './types.js';
import axios from 'axios';

export class HubSpotController {
  private config: HubSpotConfig;
  private baseUrl: string;

  constructor(config: HubSpotConfig) {
    this.config = config;
    this.baseUrl = `https://api.hubapi.com`;
  }

  async execute(action: HubSpotAction): Promise<any> {
    switch (action.action) {
      case 'getContacts':
        return this.getContacts();
      case 'getContact':
        return this.getContact(action.contactId!);
      case 'createContact':
        return this.createContact(action.data);
      case 'updateContact':
        return this.updateContact(action.contactId!, action.data);
      case 'deleteContact':
        return this.deleteContact(action.contactId!);
      case 'getDeals':
        return this.getDeals();
      case 'getDeal':
        return this.getDeal(action.dealId!);
      case 'createDeal':
        return this.createDeal(action.data);
      case 'updateDeal':
        return this.updateDeal(action.dealId!, action.data);
      case 'getCompanies':
        return this.getCompanies();
      case 'createCompany':
        return this.createCompany(action.data);
      default:
        throw new Error(`Unknown HubSpot action: ${action.action}`);
    }
  }

  private async getContacts(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/crm/v3/objects/contacts`, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, contacts: response.data.results };
    } catch (error: any) {
      throw new Error(`HubSpot getContacts failed: ${error.message}`);
    }
  }

  private async getContact(contactId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/crm/v3/objects/contacts/${contactId}`, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, contact: response.data };
    } catch (error: any) {
      throw new Error(`HubSpot getContact failed: ${error.message}`);
    }
  }

  private async createContact(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/crm/v3/objects/contacts`, data, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, contact: response.data };
    } catch (error: any) {
      throw new Error(`HubSpot createContact failed: ${error.message}`);
    }
  }

  private async updateContact(contactId: string, data: any): Promise<any> {
    try {
      const response = await axios.patch(`${this.baseUrl}/crm/v3/objects/contacts/${contactId}`, data, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, contact: response.data };
    } catch (error: any) {
      throw new Error(`HubSpot updateContact failed: ${error.message}`);
    }
  }

  private async deleteContact(contactId: string): Promise<any> {
    try {
      await axios.delete(`${this.baseUrl}/crm/v3/objects/contacts/${contactId}`, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, message: 'Contact deleted' };
    } catch (error: any) {
      throw new Error(`HubSpot deleteContact failed: ${error.message}`);
    }
  }

  private async getDeals(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/crm/v3/objects/deals`, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, deals: response.data.results };
    } catch (error: any) {
      throw new Error(`HubSpot getDeals failed: ${error.message}`);
    }
  }

  private async getDeal(dealId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/crm/v3/objects/deals/${dealId}`, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, deal: response.data };
    } catch (error: any) {
      throw new Error(`HubSpot getDeal failed: ${error.message}`);
    }
  }

  private async createDeal(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/crm/v3/objects/deals`, data, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, deal: response.data };
    } catch (error: any) {
      throw new Error(`HubSpot createDeal failed: ${error.message}`);
    }
  }

  private async updateDeal(dealId: string, data: any): Promise<any> {
    try {
      const response = await axios.patch(`${this.baseUrl}/crm/v3/objects/deals/${dealId}`, data, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, deal: response.data };
    } catch (error: any) {
      throw new Error(`HubSpot updateDeal failed: ${error.message}`);
    }
  }

  private async getCompanies(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/crm/v3/objects/companies`, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, companies: response.data.results };
    } catch (error: any) {
      throw new Error(`HubSpot getCompanies failed: ${error.message}`);
    }
  }

  private async createCompany(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/crm/v3/objects/companies`, data, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, company: response.data };
    } catch (error: any) {
      throw new Error(`HubSpot createCompany failed: ${error.message}`);
    }
  }
}
