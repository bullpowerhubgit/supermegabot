import { SendinblueConfig, SendinblueAction } from './types.js';
import SibApiV3Sdk from 'sib-api-v3-sdk';

export class SendinblueController {
  private config: SendinblueConfig;
  private client: any;

  constructor(config: SendinblueConfig) {
    this.config = config;
    this.client = SibApiV3Sdk.ApiClient.instance;
    this.client.authentications['apiKey'].apiKey = config.apiKey;
  }

  async execute(action: SendinblueAction): Promise<any> {
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
      case 'sendEmail':
        return this.sendEmail(action.data);
      case 'getCampaigns':
        return this.getCampaigns();
      case 'sendSMS':
        return this.sendSMS(action.data);
      default:
        throw new Error(`Unknown Sendinblue action: ${action.action}`);
    }
  }

  private async getContacts(): Promise<any> {
    try {
      const api = new SibApiV3Sdk.ContactsApi();
      const contacts = await api.getContacts(50);
      return { success: true, contacts: contacts.contacts };
    } catch (error: any) {
      throw new Error(`Sendinblue getContacts failed: ${error.message}`);
    }
  }

  private async getContact(contactId: string): Promise<any> {
    try {
      const api = new SibApiV3Sdk.ContactsApi();
      const contact = await api.getContactInfo(contactId);
      return { success: true, contact };
    } catch (error: any) {
      throw new Error(`Sendinblue getContact failed: ${error.message}`);
    }
  }

  private async createContact(data: any): Promise<any> {
    try {
      const api = new SibApiV3Sdk.ContactsApi();
      const contact = await api.createContact(data);
      return { success: true, contact };
    } catch (error: any) {
      throw new Error(`Sendinblue createContact failed: ${error.message}`);
    }
  }

  private async updateContact(contactId: string, data: any): Promise<any> {
    try {
      const api = new SibApiV3Sdk.ContactsApi();
      const contact = await api.updateContact(contactId, data);
      return { success: true, contact };
    } catch (error: any) {
      throw new Error(`Sendinblue updateContact failed: ${error.message}`);
    }
  }

  private async deleteContact(contactId: string): Promise<any> {
    try {
      const api = new SibApiV3Sdk.ContactsApi();
      await api.deleteContact(contactId);
      return { success: true, message: 'Contact deleted' };
    } catch (error: any) {
      throw new Error(`Sendinblue deleteContact failed: ${error.message}`);
    }
  }

  private async sendEmail(data: any): Promise<any> {
    try {
      const api = new SibApiV3Sdk.TransactionalEmailsApi();
      const result = await api.sendTransacEmail(data);
      return { success: true, result };
    } catch (error: any) {
      throw new Error(`Sendinblue sendEmail failed: ${error.message}`);
    }
  }

  private async getCampaigns(): Promise<any> {
    try {
      const api = new SibApiV3Sdk.EmailCampaignsApi();
      const campaigns = await api.getEmailCampaigns(50);
      return { success: true, campaigns: campaigns.campaigns };
    } catch (error: any) {
      throw new Error(`Sendinblue getCampaigns failed: ${error.message}`);
    }
  }

  private async sendSMS(data: any): Promise<any> {
    try {
      const api = new SibApiV3Sdk.TransactionalSMSApi();
      const result = await api.sendTransacSms(data);
      return { success: true, result };
    } catch (error: any) {
      throw new Error(`Sendinblue sendSMS failed: ${error.message}`);
    }
  }
}
