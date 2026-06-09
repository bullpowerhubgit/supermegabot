import { TwitterConfig, TwitterAction } from './types.js';
import { TwitterApi } from 'twitter-api-v2';

export class TwitterController {
  private config: TwitterConfig;
  private client: TwitterApi;

  constructor(config: TwitterConfig) {
    this.config = config;
    this.client = new TwitterApi({
      appKey: config.apiKey,
      appSecret: config.apiSecret,
      accessToken: config.accessToken,
      accessSecret: config.accessSecret,
    });
  }

  async execute(action: TwitterAction): Promise<any> {
    switch (action.action) {
      case 'getTweets':
        return this.getTweets();
      case 'getTweet':
        return this.getTweet(action.tweetId!);
      case 'createTweet':
        return this.createTweet(action.data);
      case 'deleteTweet':
        return this.deleteTweet(action.tweetId!);
      case 'getUser':
        return this.getUser(action.userId!);
      case 'getTimeline':
        return this.getTimeline();
      default:
        throw new Error(`Unknown Twitter action: ${action.action}`);
    }
  }

  private async getTweets(): Promise<any> {
    try {
      const tweets = await this.client.v2.userTimeline('me');
      return { success: true, tweets };
    } catch (error: any) {
      throw new Error(`Twitter getTweets failed: ${error.message}`);
    }
  }

  private async getTweet(tweetId: string): Promise<any> {
    try {
      const tweet = await this.client.v2.singleTweet(tweetId);
      return { success: true, tweet };
    } catch (error: any) {
      throw new Error(`Twitter getTweet failed: ${error.message}`);
    }
  }

  private async createTweet(data: any): Promise<any> {
    try {
      const tweet = await this.client.v2.tweet(data.text);
      return { success: true, tweet };
    } catch (error: any) {
      throw new Error(`Twitter createTweet failed: ${error.message}`);
    }
  }

  private async deleteTweet(tweetId: string): Promise<any> {
    try {
      await this.client.v2.deleteTweet(tweetId);
      return { success: true, message: 'Tweet deleted' };
    } catch (error: any) {
      throw new Error(`Twitter deleteTweet failed: ${error.message}`);
    }
  }

  private async getUser(userId: string): Promise<any> {
    try {
      const user = await this.client.v2.user(userId);
      return { success: true, user };
    } catch (error: any) {
      throw new Error(`Twitter getUser failed: ${error.message}`);
    }
  }

  private async getTimeline(): Promise<any> {
    try {
      const timeline = await this.client.v2.homeTimeline();
      return { success: true, timeline };
    } catch (error: any) {
      throw new Error(`Twitter getTimeline failed: ${error.message}`);
    }
  }
}
