import { CloudflareConfig, CloudflareAction } from './types.js';
import axios from 'axios';

export class CloudflareController {
  private config: CloudflareConfig;
  private baseUrl = 'https://api.cloudflare.com/client/v4';

  constructor(config: CloudflareConfig) {
    this.config = config;
  }

  async execute(action: CloudflareAction): Promise<any> {
    switch (action.action) {
      case 'listZones':
        return this.listZones();
      case 'getZone':
        return this.getZone(action.zoneId!);
      case 'getDNSRecords':
        return this.getDNSRecords(action.zoneId!);
      case 'createDNSRecord':
        return this.createDNSRecord(action.zoneId!, action.data);
      case 'updateDNSRecord':
        return this.updateDNSRecord(action.zoneId!, action.recordId!, action.data);
      case 'deleteDNSRecord':
        return this.deleteDNSRecord(action.zoneId!, action.recordId!);
      default:
        throw new Error(`Unknown Cloudflare action: ${action.action}`);
    }
  }

  private async listZones(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/zones`, {
        headers: {
          'X-Auth-Email': this.config.email,
          'X-Auth-Key': this.config.apiKey,
          'Content-Type': 'application/json',
        },
      });
      return { success: true, zones: response.data.result };
    } catch (error: any) {
      throw new Error(`Cloudflare listZones failed: ${error.message}`);
    }
  }

  private async getZone(zoneId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/zones/${zoneId}`, {
        headers: {
          'X-Auth-Email': this.config.email,
          'X-Auth-Key': this.config.apiKey,
          'Content-Type': 'application/json',
        },
      });
      return { success: true, zone: response.data.result };
    } catch (error: any) {
      throw new Error(`Cloudflare getZone failed: ${error.message}`);
    }
  }

  private async getDNSRecords(zoneId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/zones/${zoneId}/dns_records`, {
        headers: {
          'X-Auth-Email': this.config.email,
          'X-Auth-Key': this.config.apiKey,
          'Content-Type': 'application/json',
        },
      });
      return { success: true, records: response.data.result };
    } catch (error: any) {
      throw new Error(`Cloudflare getDNSRecords failed: ${error.message}`);
    }
  }

  private async createDNSRecord(zoneId: string, data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/zones/${zoneId}/dns_records`, data, {
        headers: {
          'X-Auth-Email': this.config.email,
          'X-Auth-Key': this.config.apiKey,
          'Content-Type': 'application/json',
        },
      });
      return { success: true, record: response.data.result };
    } catch (error: any) {
      throw new Error(`Cloudflare createDNSRecord failed: ${error.message}`);
    }
  }

  private async updateDNSRecord(zoneId: string, recordId: string, data: any): Promise<any> {
    try {
      const response = await axios.put(`${this.baseUrl}/zones/${zoneId}/dns_records/${recordId}`, data, {
        headers: {
          'X-Auth-Email': this.config.email,
          'X-Auth-Key': this.config.apiKey,
          'Content-Type': 'application/json',
        },
      });
      return { success: true, record: response.data.result };
    } catch (error: any) {
      throw new Error(`Cloudflare updateDNSRecord failed: ${error.message}`);
    }
  }

  private async deleteDNSRecord(zoneId: string, recordId: string): Promise<any> {
    try {
      await axios.delete(`${this.baseUrl}/zones/${zoneId}/dns_records/${recordId}`, {
        headers: {
          'X-Auth-Email': this.config.email,
          'X-Auth-Key': this.config.apiKey,
          'Content-Type': 'application/json',
        },
      });
      return { success: true, message: 'DNS record deleted' };
    } catch (error: any) {
      throw new Error(`Cloudflare deleteDNSRecord failed: ${error.message}`);
    }
  }
}
