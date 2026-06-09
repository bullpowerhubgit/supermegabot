import { InstagramConfig, InstagramAction } from './types.js';
import axios from 'axios';

export class InstagramController {
  private config: InstagramConfig;
  private baseUrl = 'https://graph.facebook.com/v18.0';

  constructor(config: InstagramConfig) {
    this.config = config;
  }

  async execute(action: InstagramAction): Promise<any> {
    switch (action.action) {
      case 'getPosts':
        return this.getPosts();
      case 'getPost':
        return this.getPost(action.mediaId!);
      case 'createPost':
        return this.createPost(action.data);
      case 'getStories':
        return this.getStories();
      case 'getMedia':
        return this.getMedia();
      default:
        throw new Error(`Unknown Instagram action: ${action.action}`);
    }
  }

  private async getPosts(): Promise<any> {
    try {
      const accountId = this.config.businessAccountId || 'me';
      const response = await axios.get(`${this.baseUrl}/${accountId}/media`, {
        params: { access_token: this.config.accessToken },
      });
      return { success: true, posts: response.data.data };
    } catch (error: any) {
      throw new Error(`Instagram getPosts failed: ${error.message}`);
    }
  }

  private async getPost(mediaId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/${mediaId}`, {
        params: { 
          access_token: this.config.accessToken,
          fields: 'id,caption,media_type,media_url',
        },
      });
      return { success: true, post: response.data };
    } catch (error: any) {
      throw new Error(`Instagram getPost failed: ${error.message}`);
    }
  }

  private async createPost(data: any): Promise<any> {
    try {
      const accountId = this.config.businessAccountId || 'me';
      const response = await axios.post(`${this.baseUrl}/${accountId}/media`, null, {
        params: { 
          access_token: this.config.accessToken,
          image_url: data.imageUrl,
          caption: data.caption,
        },
      });
      const mediaId = response.data.id;
      
      const publishResponse = await axios.post(`${this.baseUrl}/${accountId}/media_publish`, null, {
        params: { 
          access_token: this.config.accessToken,
          creation_id: mediaId,
        },
      });
      return { success: true, post: publishResponse.data };
    } catch (error: any) {
      throw new Error(`Instagram createPost failed: ${error.message}`);
    }
  }

  private async getStories(): Promise<any> {
    try {
      const accountId = this.config.businessAccountId || 'me';
      const response = await axios.get(`${this.baseUrl}/${accountId}/stories`, {
        params: { access_token: this.config.accessToken },
      });
      return { success: true, stories: response.data.data };
    } catch (error: any) {
      throw new Error(`Instagram getStories failed: ${error.message}`);
    }
  }

  private async getMedia(): Promise<any> {
    try {
      const accountId = this.config.businessAccountId || 'me';
      const response = await axios.get(`${this.baseUrl}/${accountId}/media`, {
        params: { 
          access_token: this.config.accessToken,
          fields: 'id,caption,media_type,media_url',
        },
      });
      return { success: true, media: response.data.data };
    } catch (error: any) {
      throw new Error(`Instagram getMedia failed: ${error.message}`);
    }
  }
}
