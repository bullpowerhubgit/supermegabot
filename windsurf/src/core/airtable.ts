import { AirtableConfig, AirtableAction } from './types.js';
import Airtable from 'airtable';

export class AirtableController {
  private config: AirtableConfig;
  private base: any;

  constructor(config: AirtableConfig) {
    this.config = config;
    this.base = new Airtable({ apiKey: config.apiKey }).base(config.baseId);
  }

  async execute(action: AirtableAction): Promise<any> {
    const tableName = action.tableName || this.config.tableName;

    switch (action.action) {
      case 'listTables':
        return this.listTables();
      case 'getRecords':
        return this.getRecords(tableName!);
      case 'getRecord':
        return this.getRecord(tableName!, action.recordId!);
      case 'createRecord':
        return this.createRecord(tableName!, action.data);
      case 'updateRecord':
        return this.updateRecord(tableName!, action.recordId!, action.data);
      case 'deleteRecord':
        return this.deleteRecord(tableName!, action.recordId!);
      default:
        throw new Error(`Unknown Airtable action: ${action.action}`);
    }
  }

  private async listTables(): Promise<any> {
    try {
      const tables = await this.base.tables();
      return { success: true, tables };
    } catch (error: any) {
      throw new Error(`Airtable listTables failed: ${error.message}`);
    }
  }

  private async getRecords(tableName: string): Promise<any> {
    try {
      const records = await this.base(tableName).select().all();
      return { success: true, records };
    } catch (error: any) {
      throw new Error(`Airtable getRecords failed: ${error.message}`);
    }
  }

  private async getRecord(tableName: string, recordId: string): Promise<any> {
    try {
      const record = await this.base(tableName).find(recordId);
      return { success: true, record };
    } catch (error: any) {
      throw new Error(`Airtable getRecord failed: ${error.message}`);
    }
  }

  private async createRecord(tableName: string, data: any): Promise<any> {
    try {
      const record = await this.base(tableName).create(data);
      return { success: true, record };
    } catch (error: any) {
      throw new Error(`Airtable createRecord failed: ${error.message}`);
    }
  }

  private async updateRecord(tableName: string, recordId: string, data: any): Promise<any> {
    try {
      const record = await this.base(tableName).update(recordId, data);
      return { success: true, record };
    } catch (error: any) {
      throw new Error(`Airtable updateRecord failed: ${error.message}`);
    }
  }

  private async deleteRecord(tableName: string, recordId: string): Promise<any> {
    try {
      await this.base(tableName).destroy(recordId);
      return { success: true, message: 'Record deleted' };
    } catch (error: any) {
      throw new Error(`Airtable deleteRecord failed: ${error.message}`);
    }
  }
}
