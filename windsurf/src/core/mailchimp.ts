import { MailchimpConfig, MailchimpAction } from './types.js';
import axios from 'axios';

export class MailchimpController {
  private config: MailchimpConfig;
  private baseUrl: string;

  constructor(config: MailchimpConfig) {
    this.config = config;
    const server = config.server || config.apiKey.split('-')[1];
    this.baseUrl = `https://${server}.api.mailchimp.com/3.0`;
  }

  async execute(action: MailchimpAction): Promise<any> {
    switch (action.action) {
      case 'getLists':
        return this.getLists();
      case 'getList':
        return this.getList(action.listId!);
      case 'createList':
        return this.createList(action.data);
      case 'addMember':
        return this.addMember(action.listId!, action.data);
      case 'getMembers':
        return this.getMembers(action.listId!);
      case 'getMember':
        return this.getMember(action.listId!, action.memberId!);
      case 'updateMember':
        return this.updateMember(action.listId!, action.memberId!, action.data);
      case 'deleteMember':
        return this.deleteMember(action.listId!, action.memberId!);
      case 'getCampaigns':
        return this.getCampaigns();
      case 'sendCampaign':
        return this.sendCampaign(action.campaignId!);
      default:
        throw new Error(`Unknown Mailchimp action: ${action.action}`);
    }
  }

  private async getLists(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/lists`, {
        auth: { username: 'anystring', password: this.config.apiKey },
      });
      return { success: true, lists: response.data.lists };
    } catch (error: any) {
      throw new Error(`Mailchimp getLists failed: ${error.message}`);
    }
  }

  private async getList(listId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/lists/${listId}`, {
        auth: { username: 'anystring', password: this.config.apiKey },
      });
      return { success: true, list: response.data };
    } catch (error: any) {
      throw new Error(`Mailchimp getList failed: ${error.message}`);
    }
  }

  private async createList(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/lists`, data, {
        auth: { username: 'anystring', password: this.config.apiKey },
      });
      return { success: true, list: response.data };
    } catch (error: any) {
      throw new Error(`Mailchimp createList failed: ${error.message}`);
    }
  }

  private async addMember(listId: string, data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/lists/${listId}/members`, data, {
        auth: { username: 'anystring', password: this.config.apiKey },
      });
      return { success: true, member: response.data };
    } catch (error: any) {
      throw new Error(`Mailchimp addMember failed: ${error.message}`);
    }
  }

  private async getMembers(listId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/lists/${listId}/members`, {
        auth: { username: 'anystring', password: this.config.apiKey },
      });
      return { success: true, members: response.data.members };
    } catch (error: any) {
      throw new Error(`Mailchimp getMembers failed: ${error.message}`);
    }
  }

  private async getMember(listId: string, memberId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/lists/${listId}/members/${memberId}`, {
        auth: { username: 'anystring', password: this.config.apiKey },
      });
      return { success: true, member: response.data };
    } catch (error: any) {
      throw new Error(`Mailchimp getMember failed: ${error.message}`);
    }
  }

  private async updateMember(listId: string, memberId: string, data: any): Promise<any> {
    try {
      const response = await axios.patch(`${this.baseUrl}/lists/${listId}/members/${memberId}`, data, {
        auth: { username: 'anystring', password: this.config.apiKey },
      });
      return { success: true, member: response.data };
    } catch (error: any) {
      throw new Error(`Mailchimp updateMember failed: ${error.message}`);
    }
  }

  private async deleteMember(listId: string, memberId: string): Promise<any> {
    try {
      await axios.delete(`${this.baseUrl}/lists/${listId}/members/${memberId}`, {
        auth: { username: 'anystring', password: this.config.apiKey },
      });
      return { success: true, message: 'Member deleted' };
    } catch (error: any) {
      throw new Error(`Mailchimp deleteMember failed: ${error.message}`);
    }
  }

  private async getCampaigns(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/campaigns`, {
        auth: { username: 'anystring', password: this.config.apiKey },
      });
      return { success: true, campaigns: response.data.campaigns };
    } catch (error: any) {
      throw new Error(`Mailchimp getCampaigns failed: ${error.message}`);
    }
  }

  private async sendCampaign(campaignId: string): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/campaigns/${campaignId}/actions/send`, {}, {
        auth: { username: 'anystring', password: this.config.apiKey },
      });
      return { success: true, campaign: response.data };
    } catch (error: any) {
      throw new Error(`Mailchimp sendCampaign failed: ${error.message}`);
    }
  }
}
