/**
 * Database Connection Module for My-Shop
 * Supports MongoDB and Supabase (PostgreSQL)
 */

import mongoose from 'mongoose';
import { createClient } from '@supabase/supabase-js';

class Database {
  constructor() {
    this.mongo = null;
    this.supabase = null;
    this.connected = false;
  }

  async connectMongo() {
    try {
      const uri = process.env.MONGODB_URI;
      if (!uri) {
        console.warn('[DB] MONGODB_URI not configured, using in-memory mode');
        return false;
      }

      await mongoose.connect(uri, {
        serverSelectionTimeoutMS: 5000,
        socketTimeoutMS: 45000,
      });

      this.mongo = mongoose.connection;
      this.mongo.on('error', (err) => console.error('[DB] MongoDB error:', err));
      this.mongo.on('disconnected', () => console.warn('[DB] MongoDB disconnected'));
      this.mongo.on('reconnected', () => console.log('[DB] MongoDB reconnected'));

      console.log('[DB] MongoDB connected');
      return true;
    } catch (error) {
      console.error('[DB] MongoDB connection failed:', error.message);
      return false;
    }
  }

  async connectSupabase() {
    try {
      const url = process.env.SUPABASE_URL;
      const key = process.env.SUPABASE_SERVICE_KEY;

      if (!url || !key || key.includes('YOUR_')) {
        console.warn('[DB] Supabase not configured, skipping');
        return false;
      }

      this.supabase = createClient(url, key);
      console.log('[DB] Supabase connected');
      return true;
    } catch (error) {
      console.error('[DB] Supabase connection failed:', error.message);
      return false;
    }
  }

  async connect() {
    const mongoOk = await this.connectMongo();
    const supabaseOk = await this.connectSupabase();
    this.connected = mongoOk || supabaseOk;
    return this.connected;
  }

  async disconnect() {
    if (this.mongo) {
      await mongoose.disconnect();
      console.log('[DB] MongoDB disconnected');
    }
    this.connected = false;
  }

  isConnected() {
    return this.connected;
  }

  getMongo() {
    return this.mongo;
  }

  getSupabase() {
    return this.supabase;
  }
}

export default new Database();
