import { YouTubeConfig, YouTubeAction } from './types.js';
import axios from 'axios';

export class YouTubeController {
  private config: YouTubeConfig;
  private baseUrl = 'https://www.googleapis.com/youtube/v3';

  constructor(config: YouTubeConfig) {
    this.config = config;
  }

  async execute(action: YouTubeAction): Promise<any> {
    switch (action.action) {
      case 'getVideos':
        return this.getVideos(action.channelId);
      case 'getVideo':
        return this.getVideo(action.videoId!);
      case 'getComments':
        return this.getComments(action.videoId!);
      case 'uploadVideo':
        return this.uploadVideo(action.data);
      case 'getChannels':
        return this.getChannels();
      default:
        throw new Error(`Unknown YouTube action: ${action.action}`);
    }
  }

  private async getVideos(channelId?: string): Promise<any> {
    try {
      const params: any = { key: this.config.apiKey, part: 'snippet' };
      if (channelId) params.channelId = channelId;
      const response = await axios.get(`${this.baseUrl}/videos`, { params });
      return { success: true, videos: response.data.items };
    } catch (error: any) {
      throw new Error(`YouTube getVideos failed: ${error.message}`);
    }
  }

  private async getVideo(videoId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/videos`, {
        params: { key: this.config.apiKey, part: 'snippet,statistics', id: videoId },
      });
      return { success: true, video: response.data.items[0] };
    } catch (error: any) {
      throw new Error(`YouTube getVideo failed: ${error.message}`);
    }
  }

  private async getComments(videoId: string): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/commentThreads`, {
        params: { key: this.config.apiKey, part: 'snippet', videoId },
      });
      return { success: true, comments: response.data.items };
    } catch (error: any) {
      throw new Error(`YouTube getComments failed: ${error.message}`);
    }
  }

  private async uploadVideo(data: any): Promise<any> {
    try {
      const response = await axios.post(`${this.baseUrl}/videos?uploadType=resumable&part=snippet,status`, data, {
        params: { key: this.config.apiKey },
        headers: { 'Content-Type': 'application/json' },
      });
      return { success: true, video: response.data };
    } catch (error: any) {
      throw new Error(`YouTube uploadVideo failed: ${error.message}`);
    }
  }

  private async getChannels(): Promise<any> {
    try {
      const response = await axios.get(`${this.baseUrl}/channels`, {
        params: { key: this.config.apiKey, part: 'snippet,statistics', mine: true },
      });
      return { success: true, channels: response.data.items };
    } catch (error: any) {
      throw new Error(`YouTube getChannels failed: ${error.message}`);
    }
  }
}
