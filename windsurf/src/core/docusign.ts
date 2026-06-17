import { DocuSignConfig, DocuSignAction } from './types.js';
import axios from 'axios';

export class DocuSignController {
  private config: DocuSignConfig;
  private baseUrl: string;
  private accessToken?: string;

  constructor(config: DocuSignConfig) {
    this.config = config;
    this.baseUrl = config.basePath || 'https://demo.docusign.net/restapi';
  }

  private async authenticate(): Promise<void> {
    if (this.accessToken) return;

    try {
      const response = await axios.post(`${this.baseUrl}/oauth/token`, {
        grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        assertion: this.generateJWT(),
      });
      this.accessToken = response.data.access_token;
    } catch (error: any) {
      throw new Error(`DocuSign authentication failed: ${error.message}`);
    }
  }

  private generateJWT(): string {
    // Simplified JWT generation - in production use proper JWT library
    return 'jwt_placeholder';
  }

  async execute(action: DocuSignAction): Promise<any> {
    await this.authenticate();

    switch (action.action) {
      case 'getEnvelopes':
        return this.getEnvelopes();
      case 'getEnvelope':
        return this.getEnvelope(action.envelopeId!);
      case 'createEnvelope':
        return this.createEnvelope(action.data);
      case 'sendEnvelope':
        return this.sendEnvelope(action.envelopeId!);
      case 'getDocuments':
        return this.getDocuments(action.envelopeId!);
      default:
        throw new Error(`Unknown DocuSign action: ${action.action}`);
    }
  }

  private async getEnvelopes(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/v2.1/accounts/${this.config.userId}/envelopes`, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, envelopes: response.data.envelopes };
    } catch (error: any) {
      throw new Error(`DocuSign getEnvelopes failed: ${error.message}`);
    }
  }

  private async getEnvelope(envelopeId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/v2.1/accounts/${this.config.userId}/envelopes/${envelopeId}`, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, envelope: response.data };
    } catch (error: any) {
      throw new Error(`DocuSign getEnvelope failed: ${error.message}`);
    }
  }

  private async createEnvelope(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/v2.1/accounts/${this.config.userId}/envelopes`, data, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, envelope: response.data };
    } catch (error: any) {
      throw new Error(`DocuSign createEnvelope failed: ${error.message}`);
    }
  }

  private async sendEnvelope(envelopeId: string): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/v2.1/accounts/${this.config.userId}/envelopes/${envelopeId}`, {}, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, envelope: response.data };
    } catch (error: any) {
      throw new Error(`DocuSign sendEnvelope failed: ${error.message}`);
    }
  }

  private async getDocuments(envelopeId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/v2.1/accounts/${this.config.userId}/envelopes/${envelopeId}/documents`, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, documents: response.data.envelopeDocuments };
    } catch (error: any) {
      throw new Error(`DocuSign getDocuments failed: ${error.message}`);
    }
  }
}
