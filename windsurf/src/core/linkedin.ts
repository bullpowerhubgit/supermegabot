import { LinkedInConfig, LinkedInAction } from './types.js';
import axios from 'axios';

export class LinkedInController {
  private config: LinkedInConfig;
  private baseUrl = 'https://api.linkedin.com/v2';

  constructor(config: LinkedInConfig) {
    this.config = config;
  }

  async execute(action: LinkedInAction): Promise<any> {
    switch (action.action) {
      case 'getProfile':
        return this.getProfile();
      case 'getPosts':
        return this.getPosts();
      case 'createPost':
        return this.createPost(action.data);
      case 'getConnections':
        return this.getConnections();
      case 'sendMessage':
        return this.sendMessage(action.data);
      default:
        throw new Error(`Unknown LinkedIn action: ${action.action}`);
    }
  }

  private async getProfile(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/me`, {
        headers: { Authorization: `Bearer ${this.config.accessToken}` },
      });
      return { success: true, profile: response.data };
    } catch (error: any) {
      throw new Error(`LinkedIn getProfile failed: ${error.message}`);
    }
  }

  private async getPosts(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/ugcPosts`, {
        headers: { Authorization: `Bearer ${this.config.accessToken}` },
      });
      return { success: true, posts: response.data.elements };
    } catch (error: any) {
      throw new Error(`LinkedIn getPosts failed: ${error.message}`);
    }
  }

  private async createPost(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/ugcPosts`, data, {
        headers: { 
          Authorization: `Bearer ${this.config.accessToken}`,
          'Content-Type': 'application/json',
        },
      });
      return { success: true, post: response.data };
    } catch (error: any) {
      throw new Error(`LinkedIn createPost failed: ${error.message}`);
    }
  }

  private async getConnections(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/connections`, {
        headers: { Authorization: `Bearer ${this.config.accessToken}` },
      });
      return { success: true, connections: response.data.elements };
    } catch (error: any) {
      throw new Error(`LinkedIn getConnections failed: ${error.message}`);
    }
  }

  private async sendMessage(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/messages`, data, {
        headers: { 
          Authorization: `Bearer ${this.config.accessToken}`,
          'Content-Type': 'application/json',
        },
      });
      return { success: true, message: response.data };
    } catch (error: any) {
      throw new Error(`LinkedIn sendMessage failed: ${error.message}`);
    }
  }
}
