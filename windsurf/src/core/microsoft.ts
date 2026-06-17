import { MicrosoftGraphConfig, MicrosoftGraphAction } from './types.js';
import axios from 'axios';

export class MicrosoftGraphController {
  private config: MicrosoftGraphConfig;
  private accessToken?: string;

  constructor(config: MicrosoftGraphConfig) {
    this.config = config;
  }

  private async authenticate(): Promise<void> {
    if (this.accessToken) return;

    try {
      const response = await axios.post(`https://login.microsoftonline.com/${this.config.tenantId}/oauth2/v2.0/token`, {
        client_id: this.config.clientId,
        client_secret: this.config.clientSecret,
        grant_type: 'client_credentials',
        scope: 'https://graph.microsoft.com/.default',
      });
      this.accessToken = response.data.access_token;
    } catch (error: any) {
      throw new Error(`Microsoft Graph authentication failed: ${error.message}`);
    }
  }

  async execute(action: MicrosoftGraphAction): Promise<any> {
    await this.authenticate();

    switch (action.action) {
      case 'getFiles':
        return this.getFiles(action.driveId, action.folderId);
      case 'getFile':
        return this.getFile(action.driveId, action.itemId!);
      case 'uploadFile':
        return this.uploadFile(action.driveId, action.folderId, action.data);
      case 'deleteFile':
        return this.deleteFile(action.driveId, action.itemId!);
      case 'getMessages':
        return this.getMessages();
      case 'sendMessage':
        return this.sendMessage(action.data);
      case 'getEvents':
        return this.getEvents();
      case 'createEvent':
        return this.createEvent(action.data);
      default:
        throw new Error(`Unknown Microsoft Graph action: ${action.action}`);
    }
  }

  private async getFiles(driveId?: string, folderId?: string): Promise<any> {
    try {
      const url = driveId 
        ? `https://graph.microsoft.com/v1.0/drives/${driveId}/items/${folderId || 'root'}/children`
        : `https://graph.microsoft.com/v1.0/me/drive/items/${folderId || 'root'}/children`;
      const response = await axios.get(url, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, files: response.data.value };
    } catch (error: any) {
      throw new Error(`Microsoft Graph getFiles failed: ${error.message}`);
    }
  }

  private async getFile(driveId?: string, itemId?: string): Promise<any> {
    try {
      const url = driveId 
        ? `https://graph.microsoft.com/v1.0/drives/${driveId}/items/${itemId}`
        : `https://graph.microsoft.com/v1.0/me/drive/items/${itemId}`;
      const response = await axios.get(url, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, file: response.data };
    } catch (error: any) {
      throw new Error(`Microsoft Graph getFile failed: ${error.message}`);
    }
  }

  private async uploadFile(driveId?: string, folderId?: string, data?: any): Promise<any> {
    try {
      const url = driveId 
        ? `https://graph.microsoft.com/v1.0/drives/${driveId}/items/${folderId || 'root'}:/${data.name}:/content`
        : `https://graph.microsoft.com/v1.0/me/drive/items/${folderId || 'root'}:/${data.name}:/content`;
      const response = await axios.put(url, data.content, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, file: response.data };
    } catch (error: any) {
      throw new Error(`Microsoft Graph uploadFile failed: ${error.message}`);
    }
  }

  private async deleteFile(driveId?: string, itemId?: string): Promise<any> {
    try {
      const url = driveId 
        ? `https://graph.microsoft.com/v1.0/drives/${driveId}/items/${itemId}`
        : `https://graph.microsoft.com/v1.0/me/drive/items/${itemId}`;
      await axios.delete(url, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, message: 'File deleted' };
    } catch (error: any) {
      throw new Error(`Microsoft Graph deleteFile failed: ${error.message}`);
    }
  }

  private async getMessages(): Promise<any> {
    try {
      const response = await axios.get('https://graph.microsoft.com/v1.0/me/messages', {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, messages: response.data.value };
    } catch (error: any) {
      throw new Error(`Microsoft Graph getMessages failed: ${error.message}`);
    }
  }

  private async sendMessage(data: any): Promise<any> {
    try {
      const response = await axios.post('https://graph.microsoft.com/v1.0/me/sendMail', data, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, message: response.data };
    } catch (error: any) {
      throw new Error(`Microsoft Graph sendMessage failed: ${error.message}`);
    }
  }

  private async getEvents(): Promise<any> {
    try {
      const response = await axios.get('https://graph.microsoft.com/v1.0/me/events', {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, events: response.data.value };
    } catch (error: any) {
      throw new Error(`Microsoft Graph getEvents failed: ${error.message}`);
    }
  }

  private async createEvent(data: any): Promise<any> {
    try {
      const response = await axios.post('https://graph.microsoft.com/v1.0/me/events', data, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, event: response.data };
    } catch (error: any) {
      throw new Error(`Microsoft Graph createEvent failed: ${error.message}`);
    }
  }
}
