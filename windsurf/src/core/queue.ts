import { QueueConfig, QueueAction } from './types.js';
import Queue from 'bull';
import { createClient } from 'redis';

export class QueueController {
  private config: QueueConfig;
  private queues: Map<string, Queue.Queue>;
  private redisClient?: ReturnType<typeof createClient>;

  constructor(config: QueueConfig) {
    this.config = config;
    this.queues = new Map();
  }

  private async getRedisConnection() {
    if (!this.redisClient) {
      this.redisClient = createClient({
        socket: {
          host: this.config.redisHost || 'localhost',
          port: this.config.redisPort || 6379,
        },
        password: this.config.redisPassword,
      });
      await this.redisClient.connect();
    }
    return this.redisClient;
  }

  private getQueue(queueName: string): Queue.Queue {
    if (!this.queues.has(queueName)) {
      const queue = new Queue(queueName, {
        redis: {
          host: this.config.redisHost || 'localhost',
          port: this.config.redisPort || 6379,
          password: this.config.redisPassword,
        },
      });
      this.queues.set(queueName, queue);
    }
    return this.queues.get(queueName)!;
  }

  async execute(action: QueueAction): Promise<any> {
    switch (action.action) {
      case 'addJob':
        return this.addJob(action);
      case 'processJob':
        return this.processJob(action);
      case 'getJob':
        return this.getJob(action);
      case 'removeJob':
        return this.removeJob(action);
      case 'getQueueStats':
        return this.getQueueStats(action);
      default:
        throw new Error(`Unknown queue action: ${action.action}`);
    }
  }

  private async addJob(action: QueueAction): Promise<any> {
    try {
      const queue = this.getQueue(action.queueName);
      const job = await queue.add(action.jobName || 'default', action.data || {});
      return { success: true, jobId: job.id, message: 'Job added to queue' };
    } catch (error: any) {
      throw new Error(`Job addition failed: ${error.message}`);
    }
  }

  private async processJob(action: QueueAction): Promise<any> {
    try {
      const queue = this.getQueue(action.queueName);
      queue.process(async (job) => {
        // Process job logic would be implemented here
        console.log(`Processing job ${job.id}`);
        return { success: true };
      });
      return { success: true, message: 'Job processor registered' };
    } catch (error: any) {
      throw new Error(`Job processor registration failed: ${error.message}`);
    }
  }

  private async getJob(action: QueueAction): Promise<any> {
    try {
      const queue = this.getQueue(action.queueName);
      const job = await queue.getJob(action.jobId!);
      if (!job) {
        throw new Error('Job not found');
      }
      const state = await job.getState();
      return { success: true, job: { id: job.id, data: job.data, state } };
    } catch (error: any) {
      throw new Error(`Job retrieval failed: ${error.message}`);
    }
  }

  private async removeJob(action: QueueAction): Promise<any> {
    try {
      const queue = this.getQueue(action.queueName);
      const job = await queue.getJob(action.jobId!);
      if (job) {
        await job.remove();
        return { success: true, message: 'Job removed' };
      }
      throw new Error('Job not found');
    } catch (error: any) {
      throw new Error(`Job removal failed: ${error.message}`);
    }
  }

  private async getQueueStats(action: QueueAction): Promise<any> {
    try {
      const queue = this.getQueue(action.queueName);
      const counts = await queue.getJobCounts();
      return { success: true, counts };
    } catch (error: any) {
      throw new Error(`Queue stats retrieval failed: ${error.message}`);
    }
  }

  async close(): Promise<void> {
    for (const queue of this.queues.values()) {
      await queue.close();
    }
    if (this.redisClient) {
      await this.redisClient.quit();
    }
  }
}
