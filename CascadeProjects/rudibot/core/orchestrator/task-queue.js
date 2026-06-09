const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

class TaskQueue {
  constructor(options = {}) {
    this.storagePath = options.storagePath || path.join(__dirname, '../../state/jobs');
    this.maxSize = options.maxSize || 1000;
    this.retryAttempts = options.retryAttempts || 3;
    this.logger = options.logger || console;
    this.ensureStorageDir();
  }

  ensureStorageDir() {
    if (!fs.existsSync(this.storagePath)) {
      fs.mkdirSync(this.storagePath, { recursive: true });
    }
  }

  async enqueue(job) {
    // Check queue size limit
    const currentSize = await this.getQueueSize();
    if (currentSize >= this.maxSize) {
      throw new Error('Task queue is full');
    }

    const task = {
      id: crypto.randomUUID(),
      job,
      status: 'queued',
      queuedAt: new Date().toISOString(),
      attempts: 0,
      maxAttempts: this.retryAttempts,
      lastError: null,
      completedAt: null,
      correlationId: job.correlationId
    };

    await this.saveTask(task);

    this.logger.info?.('task.queued', {
      taskId: task.id,
      jobId: job.jobId,
      action: job.action,
      correlationId: job.correlationId
    });

    return {
      status: 'queued',
      taskId: task.id,
      queuePosition: await this.getQueuePosition(task.id)
    };
  }

  async dequeue() {
    try {
      const files = fs.readdirSync(this.storagePath);
      const tasks = [];

      for (const file of files) {
        if (file.endsWith('.json')) {
          const content = fs.readFileSync(path.join(this.storagePath, file), 'utf8');
          const task = JSON.parse(content);
          
          if (task.status === 'queued') {
            tasks.push(task);
          }
        }
      }

      if (tasks.length === 0) {
        return null;
      }

      // Sort by queuedAt (FIFO)
      tasks.sort((a, b) => new Date(a.queuedAt) - new Date(b.queuedAt));
      
      const task = tasks[0];
      
      // Update status to running
      task.status = 'running';
      task.startedAt = new Date().toISOString();
      await this.saveTask(task);

      this.logger.info?.('task.dequeued', {
        taskId: task.id,
        jobId: task.job.jobId,
        action: task.job.action,
        correlationId: task.correlationId
      });

      return task;
    } catch (err) {
      this.logger.error?.('task.dequeue.failed', { error: err.message });
      return null;
    }
  }

  async complete(taskId, result = null) {
    const task = await this.getTask(taskId);
    if (!task) {
      throw new Error(`Task ${taskId} not found`);
    }

    task.status = 'completed';
    task.completedAt = new Date().toISOString();
    task.result = result;

    await this.saveTask(task);

    this.logger.info?.('task.completed', {
      taskId,
      jobId: task.job.jobId,
      action: task.job.action,
      correlationId: task.correlationId
    });

    return task;
  }

  async fail(taskId, error) {
    const task = await this.getTask(taskId);
    if (!task) {
      throw new Error(`Task ${taskId} not found`);
    }

    task.attempts++;
    task.lastError = error.message || String(error);
    task.lastErrorAt = new Date().toISOString();

    if (task.attempts >= task.maxAttempts) {
      task.status = 'failed';
      task.failedAt = new Date().toISOString();
    } else {
      task.status = 'queued'; // Re-queue for retry
    }

    await this.saveTask(task);

    this.logger.warn?.('task.failed', {
      taskId,
      jobId: task.job.jobId,
      action: task.job.action,
      attempt: task.attempts,
      maxAttempts: task.maxAttempts,
      error: task.lastError,
      correlationId: task.correlationId
    });

    return task;
  }

  async getStatus(taskId) {
    const task = await this.getTask(taskId);
    if (!task) {
      return { status: 'not_found' };
    }

    return {
      status: task.status,
      taskId: task.id,
      jobId: task.job.jobId,
      action: task.job.action,
      queuedAt: task.queuedAt,
      startedAt: task.startedAt,
      completedAt: task.completedAt,
      attempts: task.attempts,
      maxAttempts: task.maxAttempts,
      lastError: task.lastError,
      correlationId: task.correlationId
    };
  }

  async getTask(taskId) {
    try {
      const filePath = path.join(this.storagePath, `${taskId}.json`);
      if (!fs.existsSync(filePath)) {
        return null;
      }

      const content = fs.readFileSync(filePath, 'utf8');
      return JSON.parse(content);
    } catch (err) {
      this.logger.error?.('task.get.failed', { taskId, error: err.message });
      return null;
    }
  }

  async saveTask(task) {
    const filePath = path.join(this.storagePath, `${task.id}.json`);
    fs.writeFileSync(filePath, JSON.stringify(task, null, 2));
  }

  async getQueueSize() {
    try {
      const files = fs.readdirSync(this.storagePath);
      let count = 0;

      for (const file of files) {
        if (file.endsWith('.json')) {
          const content = fs.readFileSync(path.join(this.storagePath, file), 'utf8');
          const task = JSON.parse(content);
          
          if (task.status === 'queued') {
            count++;
          }
        }
      }

      return count;
    } catch (err) {
      this.logger.error?.('task.queue_size.failed', { error: err.message });
      return 0;
    }
  }

  async getQueuePosition(taskId) {
    try {
      const files = fs.readdirSync(this.storagePath);
      const queuedTasks = [];

      for (const file of files) {
        if (file.endsWith('.json')) {
          const content = fs.readFileSync(path.join(this.storagePath, file), 'utf8');
          const task = JSON.parse(content);
          
          if (task.status === 'queued') {
            queuedTasks.push(task);
          }
        }
      }

      // Sort by queuedAt
      queuedTasks.sort((a, b) => new Date(a.queuedAt) - new Date(b.queuedAt));
      
      const position = queuedTasks.findIndex(task => task.id === taskId);
      return position >= 0 ? position + 1 : -1;
    } catch (err) {
      this.logger.error?.('task.queue_position.failed', { taskId, error: err.message });
      return -1;
    }
  }

  async getQueueStats() {
    try {
      const files = fs.readdirSync(this.storagePath);
      const stats = {
        total: 0,
        queued: 0,
        running: 0,
        completed: 0,
        failed: 0
      };

      for (const file of files) {
        if (file.endsWith('.json')) {
          const content = fs.readFileSync(path.join(this.storagePath, file), 'utf8');
          const task = JSON.parse(content);
          
          stats.total++;
          stats[task.status] = (stats[task.status] || 0) + 1;
        }
      }

      return stats;
    } catch (err) {
      this.logger.error?.('task.queue_stats.failed', { error: err.message });
      return { total: 0, queued: 0, running: 0, completed: 0, failed: 0 };
    }
  }

  async cleanup(maxAge = 7 * 24 * 60 * 60 * 1000) { // 7 days default
    try {
      const files = fs.readdirSync(this.storagePath);
      const cutoff = Date.now() - maxAge;
      let cleaned = 0;

      for (const file of files) {
        if (file.endsWith('.json')) {
          const filePath = path.join(this.storagePath, file);
          const content = fs.readFileSync(filePath, 'utf8');
          const task = JSON.parse(content);

          const taskTime = new Date(task.queuedAt).getTime();
          if (taskTime < cutoff && (task.status === 'completed' || task.status === 'failed')) {
            fs.unlinkSync(filePath);
            cleaned++;
          }
        }
      }

      if (cleaned > 0) {
        this.logger.info?.('task.cleanup.completed', { cleaned, maxAge });
      }

      return cleaned;
    } catch (err) {
      this.logger.error?.('task.cleanup.failed', { error: err.message });
      return 0;
    }
  }
}

module.exports = { TaskQueue };
