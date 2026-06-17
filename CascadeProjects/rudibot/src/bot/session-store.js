/**
 * Session Store — Manages KIVO user sessions and conversation context
 * Persists session data across messages and interactions
 */

const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(process.cwd(), 'data');
const SESSION_FILE = path.join(DATA_DIR, 'user-memory.json');

function ensureDir(dir) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

class SessionStore {
  constructor(options = {}) {
    this.config = {
      sessionTimeout: options.sessionTimeout || 5 * 60 * 1000, // 5 minutes
      maxSessionHistory: options.maxSessionHistory || 100,
      ...options
    };

    this.sessions = new Map();
    this.loadSessions();
  }

  loadSessions() {
    ensureDir(DATA_DIR);
    if (fs.existsSync(SESSION_FILE)) {
      try {
        const data = JSON.parse(fs.readFileSync(SESSION_FILE, 'utf8'));
        // Restore as Map
        for (const [key, value] of Object.entries(data)) {
          this.sessions.set(key, value);
        }
      } catch (e) {
        console.warn('[SessionStore] Corrupt session file, starting fresh');
      }
    }
  }

  saveSessions() {
    ensureDir(DATA_DIR);
    const obj = {};
    for (const [key, value] of this.sessions) {
      obj[key] = value;
    }
    fs.writeFileSync(SESSION_FILE, JSON.stringify(obj, null, 2));
  }

  // ── Session Management ─────────────────────────────────────
  getOrCreateSession(chatId) {
    const sessionId = String(chatId);
    
    if (this.sessions.has(sessionId)) {
      const session = this.sessions.get(sessionId);
      
      // Check if session expired
      const now = Date.now();
      if (now - session.lastActivity > this.config.sessionTimeout) {
        session.isNew = true;
        session.context = {};
        session.history = session.history.slice(-10); // Keep last 10
      }
      
      session.lastActivity = now;
      session.isNew = false;
      return session;
    }

    // Create new session
    const newSession = {
      id: sessionId,
      createdAt: Date.now(),
      lastActivity: Date.now(),
      isNew: true,
      context: {},
      history: [],
      pendingApprovals: {},
      preferences: {}
    };

    this.sessions.set(sessionId, newSession);
    return newSession;
  }

  updateSession(chatId, updates) {
    const session = this.getOrCreateSession(chatId);
    Object.assign(session, updates);
    session.lastActivity = Date.now();
    this.saveSessions();
    return session;
  }

  endSession(chatId) {
    const sessionId = String(chatId);
    const session = this.sessions.get(sessionId);
    
    if (session) {
      session.endedAt = Date.now();
      session.active = false;
      this.saveSessions();
    }
  }

  deleteSession(chatId) {
    const sessionId = String(chatId);
    this.sessions.delete(sessionId);
    this.saveSessions();
  }

  // ── Context Management ─────────────────────────────────────
  setContext(chatId, key, value) {
    const session = this.getOrCreateSession(chatId);
    session.context[key] = value;
    session.lastActivity = Date.now();
    this.saveSessions();
  }

  getContext(chatId, key = null) {
    const session = this.getOrCreateSession(chatId);
    if (!key) return session.context;
    return session.context[key];
  }

  clearContext(chatId, key = null) {
    const session = this.getOrCreateSession(chatId);
    if (key) {
      delete session.context[key];
    } else {
      session.context = {};
    }
    this.saveSessions();
  }

  // ── History Management ─────────────────────────────────────
  addToHistory(chatId, entry) {
    const session = this.getOrCreateSession(chatId);
    
    const historyEntry = {
      timestamp: Date.now(),
      ...entry
    };

    session.history.push(historyEntry);

    // Trim history if needed
    if (session.history.length > this.config.maxSessionHistory) {
      session.history = session.history.slice(-this.config.maxSessionHistory);
    }

    session.lastActivity = Date.now();
    this.saveSessions();
  }

  getHistory(chatId, limit = 10) {
    const session = this.getOrCreateSession(chatId);
    return session.history.slice(-limit);
  }

  clearHistory(chatId) {
    const session = this.getOrCreateSession(chatId);
    session.history = [];
    this.saveSessions();
  }

  // ── Approval Management ────────────────────────────────────
  addPendingApproval(chatId, approval) {
    const session = this.getOrCreateSession(chatId);
    
    const approvalId = `approval_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    session.pendingApprovals[approvalId] = {
      id: approvalId,
      ...approval,
      createdAt: Date.now()
    };

    session.lastActivity = Date.now();
    this.saveSessions();

    // Auto-expire after 5 minutes
    setTimeout(() => {
      this.removePendingApproval(chatId, approvalId);
    }, 5 * 60 * 1000);

    return approvalId;
  }

  getPendingApproval(chatId, approvalId) {
    const session = this.getOrCreateSession(chatId);
    return session.pendingApprovals[approvalId] || null;
  }

  removePendingApproval(chatId, approvalId) {
    const session = this.getOrCreateSession(chatId);
    delete session.pendingApprovals[approvalId];
    this.saveSessions();
  }

  getAllPendingApprovals(chatId) {
    const session = this.getOrCreateSession(chatId);
    return Object.values(session.pendingApprovals);
  }

  // ── Preference Management ────────────────────────────────
  setPreference(chatId, key, value) {
    const session = this.getOrCreateSession(chatId);
    session.preferences[key] = value;
    session.lastActivity = Date.now();
    this.saveSessions();
  }

  getPreference(chatId, key, defaultValue = null) {
    const session = this.getOrCreateSession(chatId);
    return session.preferences[key] ?? defaultValue;
  }

  getAllPreferences(chatId) {
    const session = this.getOrCreateSession(chatId);
    return session.preferences;
  }

  // ── Conversation State ─────────────────────────────────────
  setConversationState(chatId, state) {
    const session = this.getOrCreateSession(chatId);
    session.conversationState = state;
    session.lastActivity = Date.now();
    this.saveSessions();
  }

  getConversationState(chatId) {
    const session = this.getOrCreateSession(chatId);
    return session.conversationState || 'idle';
  }

  // ── Cleanup ───────────────────────────────────────────────
  cleanupExpiredSessions(maxAge = 24 * 60 * 60 * 1000) { // 24 hours
    const now = Date.now();
    let cleaned = 0;

    for (const [sessionId, session] of this.sessions) {
      if (now - session.lastActivity > maxAge) {
        this.sessions.delete(sessionId);
        cleaned++;
      }
    }

    if (cleaned > 0) {
      this.saveSessions();
    }

    return cleaned;
  }

  // ── Statistics ────────────────────────────────────────────
  getStats() {
    const sessions = Array.from(this.sessions.values());
    
    return {
      totalSessions: sessions.length,
      activeSessions: sessions.filter(s => !s.endedAt).length,
      totalApprovals: sessions.reduce((acc, s) => acc + Object.keys(s.pendingApprovals || {}).length, 0),
      totalHistoryEntries: sessions.reduce((acc, s) => acc + (s.history?.length || 0), 0),
      file: SESSION_FILE
    };
  }

  // ── Status ───────────────────────────────────────────────
  getStatus() {
    return {
      sessions: this.sessions.size,
      sessionFile: SESSION_FILE,
      sessionTimeout: this.config.sessionTimeout,
      maxHistory: this.config.maxSessionHistory
    };
  }
}

module.exports = { SessionStore };
