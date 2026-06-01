import { EventEmitter } from 'events';

class BotEventBus extends EventEmitter {
  constructor() {
    super();
    this.setMaxListeners(50);
    this.history = [];
    this.maxHistory = 500;
  }

  publish(event, data = {}) {
    const entry = { timestamp: new Date().toISOString(), event, data };
    this.history.push(entry);
    if (this.history.length > this.maxHistory) {
      this.history = this.history.slice(-this.maxHistory);
    }
    this.emit(event, data);
    this.emit('*', { event, data });
  }

  subscribe(event, handler) {
    this.on(event, handler);
    return () => this.off(event, handler);
  }

  getRecent(event = null, limit = 50) {
    const filtered = event ? this.history.filter(h => h.event === event) : this.history;
    return filtered.slice(-limit);
  }

  clearHistory() {
    this.history = [];
  }
}

export const eventBus = new BotEventBus();
