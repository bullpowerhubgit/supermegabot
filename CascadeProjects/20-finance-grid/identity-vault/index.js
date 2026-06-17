#!/usr/bin/env node

// 🔐 IDENTITY VAULT
// Rudolf Sarkany · Secure Credential & Access Management
// ===================================================

'use strict';
require('dotenv').config();

const crypto = require('crypto');
const fs = require('fs').promises;
const path = require('path');

const VAULT_PATH = path.join(__dirname, '.vault');
const MASTER_KEY = process.env.FINANCE_GRID_MASTER_KEY || crypto.randomBytes(32).toString('hex');

// ── Encryption ─────────────────────────────────────────────────
function encrypt(text, key) {
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipher('aes-256-gcm', key);
  let encrypted = cipher.update(text, 'utf8', 'hex');
  encrypted += cipher.final('hex');
  const authTag = cipher.getAuthTag();
  return iv.toString('hex') + ':' + authTag.toString('hex') + ':' + encrypted;
}

function decrypt(encryptedData, key) {
  const [ivHex, authTagHex, encrypted] = encryptedData.split(':');
  const iv = Buffer.from(ivHex, 'hex');
  const authTag = Buffer.from(authTagHex, 'hex');
  const decipher = crypto.createDecipher('aes-256-gcm', key);
  decipher.setAuthTag(authTag);
  let decrypted = decipher.update(encrypted, 'hex', 'utf8');
  decrypted += decipher.final('utf8');
  return decrypted;
}

// ── Identity Vault ─────────────────────────────────────────────
class IdentityVault {
  constructor() {
    this.vault = new Map();
    this.initialized = false;
  }

  async init() {
    try {
      await fs.mkdir(VAULT_PATH, { recursive: true });
      await this.loadVault();
      this.initialized = true;
      console.log('🔐 Identity Vault initialized');
    } catch (error) {
      console.error('❌ Vault init error:', error.message);
      throw error;
    }
  }

  async loadVault() {
    try {
      const files = await fs.readdir(VAULT_PATH);
      for (const file of files) {
        if (file.endsWith('.enc')) {
          const key = file.replace('.enc', '');
          const encrypted = await fs.readFile(path.join(VAULT_PATH, file), 'utf8');
          this.vault.set(key, encrypted);
        }
      }
    } catch (error) {
      // Vault empty, that's ok
    }
  }

  async saveIdentity(key, data) {
    if (!this.initialized) await this.init();
    
    const encrypted = encrypt(JSON.stringify(data), MASTER_KEY);
    await fs.writeFile(path.join(VAULT_PATH, `${key}.enc`), encrypted, 'utf8');
    this.vault.set(key, encrypted);
    
    return { success: true, key, masked: this.maskKey(data) };
  }

  async getIdentity(key) {
    if (!this.initialized) await this.init();
    
    const encrypted = this.vault.get(key);
    if (!encrypted) return null;
    
    try {
      const decrypted = decrypt(encrypted, MASTER_KEY);
      return JSON.parse(decrypted);
    } catch (error) {
      console.error('❌ Decryption error:', error.message);
      return null;
    }
  }

  async listIdentities() {
    if (!this.initialized) await this.init();
    
    const identities = [];
    for (const key of this.vault.keys()) {
      const data = await this.getIdentity(key);
      if (data) {
        identities.push({
          key,
          type: data.type,
          provider: data.provider,
          created: data.created,
          masked: this.maskKey(data)
        });
      }
    }
    return identities;
  }

  async deleteIdentity(key) {
    if (!this.initialized) await this.init();
    
    try {
      await fs.unlink(path.join(VAULT_PATH, `${key}.enc`));
      this.vault.delete(key);
      return { success: true, key };
    } catch (error) {
      return { success: false, error: error.message };
    }
  }

  maskKey(data) {
    if (data.password || data.secret || data.token) {
      const val = data.password || data.secret || data.token;
      return val.substring(0, 4) + '***' + val.substring(val.length - 4);
    }
    return '***';
  }

  // ── Supported Identity Types ──────────────────────────────────
  async storePortalAccess(provider, credentials) {
    return this.saveIdentity(`portal_${provider}`, {
      type: 'portal',
      provider,
      ...credentials,
      created: new Date().toISOString()
    });
  }

  async storeBankAccess(bank, credentials) {
    return this.saveIdentity(`bank_${bank}`, {
      type: 'bank',
      provider: bank,
      ...credentials,
      created: new Date().toISOString()
    });
  }

  async storeApiKey(service, key) {
    return this.saveIdentity(`api_${service}`, {
      type: 'api_key',
      provider: service,
      key,
      created: new Date().toISOString()
    });
  }

  async storeElsterAccess(credentials) {
    return this.saveIdentity('elster', {
      type: 'tax_portal',
      provider: 'ELSTER',
      ...credentials,
      created: new Date().toISOString()
    });
  }
}

module.exports = { IdentityVault, encrypt, decrypt };

// ── CLI ─────────────────────────────────────────────────────────
if (require.main === module) {
  const vault = new IdentityVault();
  vault.init().then(() => {
    console.log('🔐 Identity Vault ready');
    console.log('Usage: node index.js <command> <args>');
  });
}
