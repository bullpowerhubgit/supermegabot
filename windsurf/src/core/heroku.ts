import { HerokuConfig, HerokuAction } from './types.js';
import Heroku from 'heroku-client';

export class HerokuController {
  private config: HerokuConfig;
  private client: Heroku;

  constructor(config: HerokuConfig) {
    this.config = config;
    this.client = new Heroku({ token: config.apiKey });
  }

  async execute(action: HerokuAction): Promise<any> {
    switch (action.action) {
      case 'getApps':
        return this.getApps();
      case 'getApp':
        return this.getApp(action.appName!);
      case 'createApp':
        return this.createApp(action.data);
      case 'deleteApp':
        return this.deleteApp(action.appName!);
      case 'getDynos':
        return this.getDynos(action.appName!);
      case 'restartDynos':
        return this.restartDynos(action.appName!);
      case 'getLogs':
        return this.getLogs(action.appName!);
      default:
        throw new Error(`Unknown Heroku action: ${action.action}`);
    }
  }

  private async getApps(): Promise<any> {
    try {
      const apps = await this.client.get('/apps');
      return { success: true, apps };
    } catch (error: any) {
      throw new Error(`Heroku getApps failed: ${error.message}`);
    }
  }

  private async getApp(appName: string): Promise<any> {
    try {
      const app = await this.client.get(`/apps/${appName}`);
      return { success: true, app };
    } catch (error: any) {
      throw new Error(`Heroku getApp failed: ${error.message}`);
    }
  }

  private async createApp(data: any): Promise<any> {
    try {
      const app = await this.client.post('/apps', { body: data });
      return { success: true, app };
    } catch (error: any) {
      throw new Error(`Heroku createApp failed: ${error.message}`);
    }
  }

  private async deleteApp(appName: string): Promise<any> {
    try {
      await this.client.delete(`/apps/${appName}`);
      return { success: true, message: 'App deleted' };
    } catch (error: any) {
      throw new Error(`Heroku deleteApp failed: ${error.message}`);
    }
  }

  private async getDynos(appName: string): Promise<any> {
    try {
      const dynos = await this.client.get(`/apps/${appName}/dynos`);
      return { success: true, dynos };
    } catch (error: any) {
      throw new Error(`Heroku getDynos failed: ${error.message}`);
    }
  }

  private async restartDynos(appName: string): Promise<any> {
    try {
      await this.client.delete(`/apps/${appName}/dynos`);
      return { success: true, message: 'Dynos restarted' };
    } catch (error: any) {
      throw new Error(`Heroku restartDynos failed: ${error.message}`);
    }
  }

  private async getLogs(appName: string): Promise<any> {
    try {
      const logs = await this.client.get(`/apps/${appName}/log-sessions`);
      return { success: true, logs };
    } catch (error: any) {
      throw new Error(`Heroku getLogs failed: ${error.message}`);
    }
  }
}
