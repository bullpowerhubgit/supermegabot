import { PandaDocConfig, PandaDocAction } from './types.js';
import axios from 'axios';

export class PandaDocController {
  private config: PandaDocConfig;
  private baseUrl = 'https://api.pandadoc.com/public/v1';

  constructor(config: PandaDocConfig) {
    this.config = config;
  }

  async execute(action: PandaDocAction): Promise<any> {
    switch (action.action) {
      case 'getDocuments':
        return this.getDocuments();
      case 'getDocument':
        return this.getDocument(action.documentId!);
      case 'createDocument':
        return this.createDocument(action.data);
      case 'sendDocument':
        return this.sendDocument(action.documentId!);
      case 'getTemplates':
        return this.getTemplates();
      default:
        throw new Error(`Unknown PandaDoc action: ${action.action}`);
    }
  }

  private async getDocuments(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/documents`, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, documents: response.data.results };
    } catch (error: any) {
      throw new Error(`PandaDoc getDocuments failed: ${error.message}`);
    }
  }

  private async getDocument(documentId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/documents/${documentId}`, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, document: response.data };
    } catch (error: any) {
      throw new Error(`PandaDoc getDocument failed: ${error.message}`);
    }
  }

  private async createDocument(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/documents`, data, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, document: response.data };
    } catch (error: any) {
      throw new Error(`PandaDoc createDocument failed: ${error.message}`);
    }
  }

  private async sendDocument(documentId: string): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/documents/${documentId}/send`, {}, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, document: response.data };
    } catch (error: any) {
      throw new Error(`PandaDoc sendDocument failed: ${error.message}`);
    }
  }

  private async getTemplates(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/templates`, {
        headers: { Authorization: `Bearer ${this.config.apiKey}` },
      });
      return { success: true, templates: response.data.results };
    } catch (error: any) {
      throw new Error(`PandaDoc getTemplates failed: ${error.message}`);
    }
  }
}
