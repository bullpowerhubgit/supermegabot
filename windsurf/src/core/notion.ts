import { NotionConfig, NotionAction } from './types.js';
import { Client } from '@notionhq/client';

export class NotionController {
  private config: NotionConfig;
  private client: Client;

  constructor(config: NotionConfig) {
    this.config = config;
    this.client = new Client({ auth: config.token });
  }

  async execute(action: NotionAction): Promise<any> {
    switch (action.action) {
      case 'getDatabases':
        return this.getDatabases();
      case 'getDatabase':
        return this.getDatabase(action.databaseId!);
      case 'queryDatabase':
        return this.queryDatabase(action.databaseId!, action.query);
      case 'getPage':
        return this.getPage(action.pageId!);
      case 'createPage':
        return this.createPage(action.data);
      case 'updatePage':
        return this.updatePage(action.pageId!, action.data);
      case 'deletePage':
        return this.deletePage(action.pageId!);
      default:
        throw new Error(`Unknown Notion action: ${action.action}`);
    }
  }

  private async getDatabases(): Promise<any> {
    try {
      const response = await this.client.search({ filter: { property: 'object', value: 'database' } });
      return { success: true, databases: response.results };
    } catch (error: any) {
      throw new Error(`Notion getDatabases failed: ${error.message}`);
    }
  }

  private async getDatabase(databaseId: string): Promise<any> {
    try {
      const database = await this.client.databases.retrieve({ database_id: databaseId });
      return { success: true, database };
    } catch (error: any) {
      throw new Error(`Notion getDatabase failed: ${error.message}`);
    }
  }

  private async queryDatabase(databaseId: string, query?: any): Promise<any> {
    try {
      const response = await this.client.databases.query({ database_id: databaseId, ...query });
      return { success: true, results: response.results };
    } catch (error: any) {
      throw new Error(`Notion queryDatabase failed: ${error.message}`);
    }
  }

  private async getPage(pageId: string): Promise<any> {
    try {
      const page = await this.client.pages.retrieve({ page_id: pageId });
      return { success: true, page };
    } catch (error: any) {
      throw new Error(`Notion getPage failed: ${error.message}`);
    }
  }

  private async createPage(data: any): Promise<any> {
    try {
      const page = await this.client.pages.create(data);
      return { success: true, page };
    } catch (error: any) {
      throw new Error(`Notion createPage failed: ${error.message}`);
    }
  }

  private async updatePage(pageId: string, data: any): Promise<any> {
    try {
      const page = await this.client.pages.update({ page_id: pageId, ...data });
      return { success: true, page };
    } catch (error: any) {
      throw new Error(`Notion updatePage failed: ${error.message}`);
    }
  }

  private async deletePage(pageId: string): Promise<any> {
    try {
      const page = await this.client.pages.update({ page_id: pageId, archived: true });
      return { success: true, page };
    } catch (error: any) {
      throw new Error(`Notion deletePage failed: ${error.message}`);
    }
  }
}
