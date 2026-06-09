import { FacebookConfig, FacebookAction } from './types.js';
import axios from 'axios';

export class FacebookController {
  private config: FacebookConfig;
  private baseUrl = 'https://graph.facebook.com/v18.0';

  constructor(config: FacebookConfig) {
    this.config = config;
  }

  async execute(action: FacebookAction): Promise<any> {
    switch (action.action) {
      case 'getPosts':
        return this.getPosts(action.pageId);
      case 'getPost':
        return this.getPost(action.postId!);
      case 'createPost':
        return this.createPost(action.pageId!, action.data);
      case 'deletePost':
        return this.deletePost(action.postId!);
      case 'getPages':
        return this.getPages();
      case 'getPage':
        return this.getPage(action.pageId!);
      case 'getAds':
        return this.getAds();
      default:
        throw new Error(`Unknown Facebook action: ${action.action}`);
    }
  }

  private async getPosts(pageId?: string): Promise<any> {
    try {
      const url = pageId 
        ? `${this.baseUrl}/${pageId}/posts`
        : `${this.baseUrl}/me/posts`;
      const response = await axios.get(url, {
        params: { access_token: this.config.accessToken },
      });
      return { success: true, posts: response.data.data };
    } catch (error: any) {
      throw new Error(`Facebook getPosts failed: ${error.message}`);
    }
  }

  private async getPost(postId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/${postId}`, {
        params: { access_token: this.config.accessToken },
      });
      return { success: true, post: response.data };
    } catch (error: any) {
      throw new Error(`Facebook getPost failed: ${error.message}`);
    }
  }

  private async createPost(pageId: string, data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/${pageId}/feed`, null, {
        params: { access_token: this.config.accessToken, ...data },
      });
      return { success: true, post: response.data };
    } catch (error: any) {
      throw new Error(`Facebook createPost failed: ${error.message}`);
    }
  }

  private async deletePost(postId: string): Promise<any> {
    try {
      await axios.delete(`${this.baseUrl}/${postId}`, {
        params: { access_token: this.config.accessToken },
      });
      return { success: true, message: 'Post deleted' };
    } catch (error: any) {
      throw new Error(`Facebook deletePost failed: ${error.message}`);
    }
  }

  private async getPages(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/me/accounts`, {
        params: { access_token: this.config.accessToken },
      });
      return { success: true, pages: response.data.data };
    } catch (error: any) {
      throw new Error(`Facebook getPages failed: ${error.message}`);
    }
  }

  private async getPage(pageId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/${pageId}`, {
        params: { access_token: this.config.accessToken },
      });
      return { success: true, page: response.data };
    } catch (error: any) {
      throw new Error(`Facebook getPage failed: ${error.message}`);
    }
  }

  private async getAds(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/me/adaccounts`, {
        params: { access_token: this.config.accessToken },
      });
      return { success: true, ads: response.data.data };
    } catch (error: any) {
      throw new Error(`Facebook getAds failed: ${error.message}`);
    }
  }
}
