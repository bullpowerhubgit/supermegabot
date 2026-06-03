/**
 * Allowed Users Configuration — Authorized Telegram user IDs
 * Manages user whitelist and access control
 */

const fs = require('fs');
const path = require('path');

const CONFIG_DIR = path.join(__dirname);
const USERS_FILE = path.join(CONFIG_DIR, 'allowed-users.json');

class AllowedUsers {
  constructor(options = {}) {
    this.users = new Map();
    this.strictMode = options.strictMode !== false; // Default: strict
    this.loadUsers();
  }

  loadUsers() {
    // Load from environment
    if (process.env.ALLOWED_USER_IDS) {
      const ids = process.env.ALLOWED_USER_IDS.split(',').map(id => id.trim());
      for (const id of ids) {
        this.users.set(id, {
          id,
          role: 'user',
          addedAt: new Date().toISOString(),
          source: 'env'
        });
      }
    }

    // Load from file
    if (fs.existsSync(USERS_FILE)) {
      try {
        const data = JSON.parse(fs.readFileSync(USERS_FILE, 'utf8'));
        for (const user of data.users || []) {
          this.users.set(String(user.id), {
            ...user,
            source: 'file'
          });
        }
      } catch (e) {
        console.warn('[AllowedUsers] Failed to load users file:', e.message);
      }
    }
  }

  saveUsers() {
    const data = {
      updatedAt: new Date().toISOString(),
      users: Array.from(this.users.values()).map(u => ({
        id: u.id,
        role: u.role,
        name: u.name,
        addedAt: u.addedAt
      }))
    };

    fs.writeFileSync(USERS_FILE, JSON.stringify(data, null, 2));
  }

  // ── User Management ────────────────────────────────────────
  isAllowed(userId) {
    if (!this.strictMode) return true;
    return this.users.has(String(userId));
  }

  addUser(userId, role = 'user', name = null) {
    const id = String(userId);
    
    if (this.users.has(id)) {
      return { success: false, error: 'User already exists' };
    }

    this.users.set(id, {
      id,
      role,
      name,
      addedAt: new Date().toISOString(),
      source: 'manual'
    });

    this.saveUsers();
    return { success: true, userId: id, role };
  }

  removeUser(userId) {
    const id = String(userId);
    
    if (!this.users.has(id)) {
      return { success: false, error: 'User not found' };
    }

    this.users.delete(id);
    this.saveUsers();
    return { success: true, userId: id };
  }

  updateUser(userId, updates) {
    const id = String(userId);
    const user = this.users.get(id);
    
    if (!user) {
      return { success: false, error: 'User not found' };
    }

    Object.assign(user, updates);
    user.updatedAt = new Date().toISOString();
    this.saveUsers();
    
    return { success: true, user };
  }

  getUser(userId) {
    return this.users.get(String(userId)) || null;
  }

  getUserRole(userId) {
    const user = this.getUser(userId);
    return user ? user.role : 'guest';
  }

  getAllUsers() {
    return Array.from(this.users.values());
  }

  getUsersByRole(role) {
    return Array.from(this.users.values()).filter(u => u.role === role);
  }

  // ── Authorization Checks ───────────────────────────────────
  canExecute(userId, intent) {
    const user = this.getUser(userId);
    if (!user) return false;

    const { canExecute } = require('./roles');
    return canExecute(user.role, intent);
  }

  canApprove(userId) {
    const user = this.getUser(userId);
    if (!user) return false;

    const { getRole } = require('./roles');
    const role = getRole(user.role);
    return role.permissions.canApprove || false;
  }

  // ── Pairing Flow ─────────────────────────────────────────
  async requestPairing(userId, adminId) {
    if (!this.isAllowed(adminId)) {
      return { success: false, error: 'Unauthorized' };
    }

    const admin = this.getUser(adminId);
    if (!['admin', 'owner'].includes(admin.role)) {
      return { success: false, error: 'Admin role required' };
    }

    return this.addUser(userId, 'user');
  }

  // ── Statistics ─────────────────────────────────────────────
  getStats() {
    const users = Array.from(this.users.values());
    
    return {
      total: users.length,
      byRole: users.reduce((acc, u) => {
        acc[u.role] = (acc[u.role] || 0) + 1;
        return acc;
      }, {}),
      strictMode: this.strictMode,
      file: USERS_FILE
    };
  }

  // ── Status ─────────────────────────────────────────────────
  getStatus() {
    return {
      configured: this.users.size > 0,
      totalUsers: this.users.size,
      strictMode: this.strictMode,
      usersFile: USERS_FILE
    };
  }
}

module.exports = { AllowedUsers };
