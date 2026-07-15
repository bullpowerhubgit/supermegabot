import { createClient } from 'redis';

let _client: ReturnType<typeof createClient> | null = null;
let redisAvailable = false;

export async function connectRedis() {
  if (!process.env.REDIS_URL) {
    console.log('Redis: REDIS_URL not set — using in-memory fallback');
    return;
  }
  try {
    _client = createClient({ url: process.env.REDIS_URL });
    _client.on('error', (err) => console.warn('Redis warning:', err.message));
    await _client.connect();
    redisAvailable = true;
    console.log('Redis connected');
  } catch (err) {
    console.warn('Redis unavailable — continuing without cache:', (err as Error).message);
  }
}

const memCache: Record<string, { v: unknown; exp: number }> = {};

export async function cacheSet(key: string, value: unknown, ttlSeconds = 300): Promise<void> {
  if (redisAvailable && _client) {
    try { await _client.setEx(key, ttlSeconds, JSON.stringify(value)); return; } catch (_) {}
  }
  memCache[key] = { v: value, exp: Date.now() + ttlSeconds * 1000 };
}

export async function cacheGet<T>(key: string): Promise<T | null> {
  if (redisAvailable && _client) {
    try {
      const val = await _client.get(key);
      return val ? JSON.parse(val) as T : null;
    } catch (_) {}
  }
  const entry = memCache[key];
  if (entry && entry.exp > Date.now()) return entry.v as T;
  return null;
}

export default { isOpen: false };
