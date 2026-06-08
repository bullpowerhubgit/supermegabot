/**
 * KIVO MEMORY — User Context, Preferences, Projects, Device Knowledge
 * Persistent memory layer for KIVO agent continuity
 */

const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(process.cwd(), 'data');
const MEMORY_FILE = path.join(DATA_DIR, 'kivo-memory.json');

function ensureDir(filePath) {
  const dir = path.dirname(filePath);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

class KivoMemory {
  constructor() {
    this.data = {
      userProfile: {},
      preferences: {},
      projects: [],
      routines: [],
      deviceKnowledge: {},
      conversationHistory: [],
      lastAccess: null,
    };
    this.load();
  }

  load() {
    if (fs.existsSync(MEMORY_FILE)) {
      try {
        this.data = JSON.parse(fs.readFileSync(MEMORY_FILE, 'utf8'));
      } catch (e) {
        console.warn('[KIVO MEMORY] Corrupt memory file, resetting.');
      }
    }
  }

  save() {
    ensureDir(MEMORY_FILE);
    fs.writeFileSync(MEMORY_FILE, JSON.stringify(this.data, null, 2));
  }

  // ── User Profile ───────────────────────────────────────────
  setUserProfile(profile) {
    this.data.userProfile = { ...this.data.userProfile, ...profile };
    this.save();
  }

  getUserProfile() {
    return this.data.userProfile;
  }

  // ── Preferences ────────────────────────────────────────────
  setPreference(key, value) {
    this.data.preferences[key] = value;
    this.save();
  }

  getPreference(key, defaultValue = null) {
    return this.data.preferences[key] ?? defaultValue;
  }

  // ── Projects ───────────────────────────────────────────────
  addProject(project) {
    const p = { id: `proj-${Date.now()}`, createdAt: new Date().toISOString(), status: 'active', tasks: [], ...project };
    this.data.projects.push(p);
    this.save();
    return p;
  }

  getProjects(status = null) {
    if (!status) return this.data.projects;
    return this.data.projects.filter(p => p.status === status);
  }

  updateProject(id, updates) {
    const idx = this.data.projects.findIndex(p => p.id === id);
    if (idx >= 0) {
      this.data.projects[idx] = { ...this.data.projects[idx], ...updates, updatedAt: new Date().toISOString() };
      this.save();
      return this.data.projects[idx];
    }
    return null;
  }

  // ── Routines ───────────────────────────────────────────────
  addRoutine(routine) {
    const r = { id: `rtn-${Date.now()}`, createdAt: new Date().toISOString(), enabled: true, ...routine };
    this.data.routines.push(r);
    this.save();
    return r;
  }

  getRoutines() {
    return this.data.routines;
  }

  // ── Device Knowledge ───────────────────────────────────────
  learnDevice(deviceId, info) {
    this.data.deviceKnowledge[deviceId] = {
      ...this.data.deviceKnowledge[deviceId],
      ...info,
      lastSeen: new Date().toISOString(),
    };
    this.save();
  }

  getDevice(deviceId) {
    return this.data.deviceKnowledge[deviceId] || null;
  }

  // ── Conversation History ───────────────────────────────────
  addConversationEntry(entry) {
    this.data.conversationHistory.push({
      timestamp: new Date().toISOString(),
      ...entry,
    });
    // Keep last 1000 entries
    if (this.data.conversationHistory.length > 1000) {
      this.data.conversationHistory = this.data.conversationHistory.slice(-1000);
    }
    this.save();
  }

  getRecentConversation(n = 10) {
    return this.data.conversationHistory.slice(-n);
  }

  // ── Context Builder ────────────────────────────────────────
  buildContext() {
    return {
      user: this.data.userProfile,
      preferences: this.data.preferences,
      activeProjects: this.getProjects('active').length,
      totalProjects: this.data.projects.length,
      routines: this.data.routines.length,
      devices: Object.keys(this.data.deviceKnowledge).length,
      recentTopics: this.extractTopics(),
    };
  }

  extractTopics() {
    // Simple topic extraction from recent conversations
    const recent = this.getRecentConversation(20);
    const topics = {};
    for (const entry of recent) {
      if (entry.intent?.type) {
        topics[entry.intent.type] = (topics[entry.intent.type] || 0) + 1;
      }
    }
    return Object.entries(topics)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([topic]) => topic);
  }

  // ── Status ─────────────────────────────────────────────────
  getStatus() {
    return {
      projects: this.data.projects.length,
      activeProjects: this.getProjects('active').length,
      routines: this.data.routines.length,
      devices: Object.keys(this.data.deviceKnowledge).length,
      conversationEntries: this.data.conversationHistory.length,
      memoryFile: MEMORY_FILE,
    };
  }
}

module.exports = { KivoMemory };
