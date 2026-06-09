import { ZohoConfig, ZohoAction } from './types.js';
import axios from 'axios';

export class ZohoController {
  private config: ZohoConfig;
  private baseUrl = 'https://www.zohoapis.com/crm/v2';

  constructor(config: ZohoConfig) {
    this.config = config;
  }

  async execute(action: ZohoAction): Promise<any> {
    switch (action.action) {
      case 'getLeads':
        return this.getLeads();
      case 'getLead':
        return this.getLead(action.leadId!);
      case 'createLead':
        return this.createLead(action.data);
      case 'updateLead':
        return this.updateLead(action.leadId!, action.data);
      case 'getContacts':
        return this.getContacts();
      case 'getContact':
        return this.getContact(action.contactId!);
      default:
        throw new Error(`Unknown Zoho action: ${action.action}`);
    }
  }

  private async getLeads(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/Leads`, {
        headers: { Authorization: `Zoho-oauthtoken ${this.config.accessToken}` },
      });
      return { success: true, leads: response.data.data };
    } catch (error: any) {
      throw new Error(`Zoho getLeads failed: ${error.message}`);
    }
  }

  private async getLead(leadId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/Leads/${leadId}`, {
        headers: { Authorization: `Zoho-oauthtoken ${this.config.accessToken}` },
      });
      return { success: true, lead: response.data.data[0] };
    } catch (error: any) {
      throw new Error(`Zoho getLead failed: ${error.message}`);
    }
  }

  private async createLead(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/Leads`, { data: [data] }, {
        headers: { Authorization: `Zoho-oauthtoken ${this.config.accessToken}` },
      });
      return { success: true, lead: response.data.data[0] };
    } catch (error: any) {
      throw new Error(`Zoho createLead failed: ${error.message}`);
    }
  }

  private async updateLead(leadId: string, data: any): Promise<any> {
    try {
      const response = await axios.put(`${this.baseUrl}/Leads/${leadId}`, { data: [data] }, {
        headers: { Authorization: `Zoho-oauthtoken ${this.config.accessToken}` },
      });
      return { success: true, lead: response.data.data[0] };
    } catch (error: any) {
      throw new Error(`Zoho updateLead failed: ${error.message}`);
    }
  }

  private async getContacts(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/Contacts`, {
        headers: { Authorization: `Zoho-oauthtoken ${this.config.accessToken}` },
      });
      return { success: true, contacts: response.data.data };
    } catch (error: any) {
      throw new Error(`Zoho getContacts failed: ${error.message}`);
    }
  }

  private async getContact(contactId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/Contacts/${contactId}`, {
        headers: { Authorization: `Zoho-oauthtoken ${this.config.accessToken}` },
      });
      return { success: true, contact: response.data.data[0] };
    } catch (error: any) {
      throw new Error(`Zoho getContact failed: ${error.message}`);
    }
  }
}
