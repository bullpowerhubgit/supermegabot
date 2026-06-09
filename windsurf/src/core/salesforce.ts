import { SalesforceConfig, SalesforceAction } from './types.js';
import axios from 'axios';

export class SalesforceController {
  private config: SalesforceConfig;
  private accessToken?: string;
  private instanceUrl?: string;

  constructor(config: SalesforceConfig) {
    this.config = config;
  }

  private async authenticate(): Promise<void> {
    if (this.accessToken) return;

    try {
      const response = await axios.post(`${this.config.loginUrl}/services/oauth2/token`, null, {
        params: {
          grant_type: 'password',
          client_id: this.config.username,
          client_secret: this.config.password,
          username: this.config.username,
          password: this.config.password + this.config.securityToken,
        },
      });
      this.accessToken = response.data.access_token;
      this.instanceUrl = response.data.instance_url;
    } catch (error: any) {
      throw new Error(`Salesforce authentication failed: ${error.message}`);
    }
  }

  async execute(action: SalesforceAction): Promise<any> {
    await this.authenticate();

    switch (action.action) {
      case 'query':
        return this.query(action.query!);
      case 'create':
        return this.create(action.object!, action.data);
      case 'update':
        return this.update(action.object!, action.recordId!, action.data);
      case 'delete':
        return this.delete(action.object!, action.recordId!);
      case 'getRecords':
        return this.getRecords(action.object!);
      case 'getRecord':
        return this.getRecord(action.object!, action.recordId!);
      default:
        throw new Error(`Unknown Salesforce action: ${action.action}`);
    }
  }

  private async query(soql: string): Promise<any> {
    try {
      const response = await axios.get(`${this.instanceUrl}/services/data/v56.0/query`, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
        params: { q: soql },
      });
      return { success: true, records: response.data.records, totalSize: response.data.totalSize };
    } catch (error: any) {
      throw new Error(`Salesforce query failed: ${error.message}`);
    }
  }

  private async create(object: string, data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.instanceUrl}/services/data/v56.0/sobjects/${object}`, data, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, record: response.data };
    } catch (error: any) {
      throw new Error(`Salesforce create failed: ${error.message}`);
    }
  }

  private async update(object: string, recordId: string, data: any): Promise<any> {
    try {
      await axios.patch(`${this.instanceUrl}/services/data/v56.0/sobjects/${object}/${recordId}`, data, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, message: 'Record updated' };
    } catch (error: any) {
      throw new Error(`Salesforce update failed: ${error.message}`);
    }
  }

  private async delete(object: string, recordId: string): Promise<any> {
    try {
      await axios.delete(`${this.instanceUrl}/services/data/v56.0/sobjects/${object}/${recordId}`, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, message: 'Record deleted' };
    } catch (error: any) {
      throw new Error(`Salesforce delete failed: ${error.message}`);
    }
  }

  private async getRecords(object: string): Promise<any> {
    try {
      const response = await axios.get(`${this.instanceUrl}/services/data/v56.0/query`, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
        params: { q: `SELECT Id, Name FROM ${object} LIMIT 100` },
      });
      return { success: true, records: response.data.records };
    } catch (error: any) {
      throw new Error(`Salesforce getRecords failed: ${error.message}`);
    }
  }

  private async getRecord(object: string, recordId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.instanceUrl}/services/data/v56.0/sobjects/${object}/${recordId}`, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
      return { success: true, record: response.data };
    } catch (error: any) {
      throw new Error(`Salesforce getRecord failed: ${error.message}`);
    }
  }
}
