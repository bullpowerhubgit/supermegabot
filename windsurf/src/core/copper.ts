import { CopperConfig, CopperAction } from './types.js';
import axios from 'axios';

export class CopperController {
  private config: CopperConfig;
  private baseUrl = 'https://api.copper.com/developer_api/v1';

  constructor(config: CopperConfig) {
    this.config = config;
  }

  private getAuth() {
    return {
      auth: {
        username: this.config.apiKey,
        password: this.config.email,
      },
    };
  }

  async execute(action: CopperAction): Promise<any> {
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
        throw new Error(`Unknown Copper action: ${action.action}`);
    }
  }

  private async getLeads(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/leads`, this.getAuth());
      return { success: true, leads: response.data };
    } catch (error: any) {
      throw new Error(`Copper getLeads failed: ${error.message}`);
    }
  }

  private async getLead(leadId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/leads/${leadId}`, this.getAuth());
      return { success: true, lead: response.data };
    } catch (error: any) {
      throw new Error(`Copper getLead failed: ${error.message}`);
    }
  }

  private async createLead(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/leads`, data, this.getAuth());
      return { success: true, lead: response.data };
    } catch (error: any) {
      throw new Error(`Copper createLead failed: ${error.message}`);
    }
  }

  private async updateLead(leadId: string, data: any): Promise<any> {
    try {
      const response = await axios.put(`${this.baseUrl}/leads/${leadId}`, data, this.getAuth());
      return { success: true, lead: response.data };
    } catch (error: any) {
      throw new Error(`Copper updateLead failed: ${error.message}`);
    }
  }

  private async getContacts(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/people`, this.getAuth());
      return { success: true, contacts: response.data };
    } catch (error: any) {
      throw new Error(`Copper getContacts failed: ${error.message}`);
    }
  }

  private async getContact(contactId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/people/${contactId}`, this.getAuth());
      return { success: true, contact: response.data };
    } catch (error: any) {
      throw new Error(`Copper getContact failed: ${error.message}`);
    }
  }
}
