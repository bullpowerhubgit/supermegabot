import { ActiveCampaignConfig, ActiveCampaignAction } from './types.js';
import axios from 'axios';

export class ActiveCampaignController {
  private config: ActiveCampaignConfig;
  private baseUrl: string;

  constructor(config: ActiveCampaignConfig) {
    this.config = config;
    this.baseUrl = config.apiUrl;
  }

  async execute(action: ActiveCampaignAction): Promise<any> {
    switch (action.action) {
      case 'getContacts':
        return this.getContacts();
      case 'getContact':
        return this.getContact(action.contactId!);
      case 'createContact':
        return this.createContact(action.data);
      case 'updateContact':
        return this.updateContact(action.contactId!, action.data);
      case 'getCampaigns':
        return this.getCampaigns();
      case 'sendEmail':
        return this.sendEmail(action.data);
      default:
        throw new Error(`Unknown ActiveCampaign action: ${action.action}`);
    }
  }

  private async getContacts(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/contacts`, {
        headers: { 'Api-Token': this.config.apiKey },
      });
      return { success: true, contacts: response.data.contacts };
    } catch (error: any) {
      throw new Error(`ActiveCampaign getContacts failed: ${error.message}`);
    }
  }

  private async getContact(contactId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/contacts/${contactId}`, {
        headers: { 'Api-Token': this.config.apiKey },
      });
      return { success: true, contact: response.data.contact };
    } catch (error: any) {
      throw new Error(`ActiveCampaign getContact failed: ${error.message}`);
    }
  }

  private async createContact(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/contacts`, { contact: data }, {
        headers: { 'Api-Token': this.config.apiKey },
      });
      return { success: true, contact: response.data.contact };
    } catch (error: any) {
      throw new Error(`ActiveCampaign createContact failed: ${error.message}`);
    }
  }

  private async updateContact(contactId: string, data: any): Promise<any> {
    try {
      const response = await axios.put(`${this.baseUrl}/contacts/${contactId}`, { contact: data }, {
        headers: { 'Api-Token': this.config.apiKey },
      });
      return { success: true, contact: response.data.contact };
    } catch (error: any) {
      throw new Error(`ActiveCampaign updateContact failed: ${error.message}`);
    }
  }

  private async getCampaigns(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/campaigns`, {
        headers: { 'Api-Token': this.config.apiKey },
      });
      return { success: true, campaigns: response.data.campaigns };
    } catch (error: any) {
      throw new Error(`ActiveCampaign getCampaigns failed: ${error.message}`);
    }
  }

  private async sendEmail(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/campaigns/${data.campaignId}/send`, data, {
        headers: { 'Api-Token': this.config.apiKey },
      });
      return { success: true, result: response.data };
    } catch (error: any) {
      throw new Error(`ActiveCampaign sendEmail failed: ${error.message}`);
    }
  }
}
