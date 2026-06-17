/**
 * KIVO HOME — Home Assistant Bridge & Smart Home Control
 * Fast path for local home automation commands
 */

const { exec } = require('child_process');
const { promisify } = require('util');
const execAsync = promisify(exec);

const HA_CONFIG = {
  baseUrl: process.env.HOME_ASSISTANT_URL || 'http://homeassistant.local:8123',
  token: process.env.HOME_ASSISTANT_TOKEN || null,
  timeout: 5000,
};

class KivoHome {
  constructor(options = {}) {
    this.config = { ...HA_CONFIG, ...options };
    this.devices = new Map();
    this.scenes = new Map();
  }

  // ── Device Registry ────────────────────────────────────────
  registerDevice(id, info) {
    this.devices.set(id, { id, ...info, lastSeen: Date.now() });
  }

  getDevice(id) {
    return this.devices.get(id) || null;
  }

  listDevices(room = null) {
    const devices = Array.from(this.devices.values());
    if (room) return devices.filter(d => d.room === room);
    return devices;
  }

  // ── Home Assistant API ───────────────────────────────────
  async haCall(service, data = {}) {
    if (!this.config.token) {
      throw new Error('HOME_ASSISTANT_TOKEN not configured');
    }
    const url = `${this.config.baseUrl}/api/services/${service}`;
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.config.token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
        signal: AbortSignal.timeout(this.config.timeout),
      });
      return await res.json();
    } catch (e) {
      return { error: e.message, offline: true };
    }
  }

  // ── Fast Path Commands ─────────────────────────────────────
  async turnOn(entityId) {
    return this.haCall('homeassistant/turn_on', { entity_id: entityId });
  }

  async turnOff(entityId) {
    return this.haCall('homeassistant/turn_off', { entity_id: entityId });
  }

  async toggle(entityId) {
    return this.haCall('homeassistant/toggle', { entity_id: entityId });
  }

  async setBrightness(entityId, brightness) {
    // brightness 0-255
    return this.haCall('light/turn_on', { entity_id: entityId, brightness });
  }

  async setTemperature(entityId, temperature) {
    return this.haCall('climate/set_temperature', { entity_id: entityId, temperature });
  }

  async setColor(entityId, color) {
    return this.haCall('light/turn_on', { entity_id: entityId, rgb_color: color });
  }

  // ── Timer / Alarm ──────────────────────────────────────────
  async setTimer(minutes, name = 'Kivo Timer') {
    // Could integrate with HA timer or local setTimeout
    const ms = minutes * 60 * 1000;
    setTimeout(() => {
      console.log(`[KIVO HOME] Timer expired: ${name}`);
    }, ms);
    return { timer: name, minutes, expiresAt: new Date(Date.now() + ms).toISOString() };
  }

  // ── Scene Activation ───────────────────────────────────────
  async activateScene(sceneId) {
    const scene = this.scenes.get(sceneId);
    if (!scene) return { error: 'Scene not found' };
    for (const action of scene.actions) {
      await this.haCall(action.service, action.data);
    }
    return { scene: sceneId, activated: true };
  }

  registerScene(id, actions) {
    this.scenes.set(id, { id, actions });
  }

  // ── Garage / Door ──────────────────────────────────────────
  async openGarage(entityId) {
    return this.haCall('cover/open_cover', { entity_id: entityId });
  }

  async closeGarage(entityId) {
    return this.haCall('cover/close_cover', { entity_id: entityId });
  }

  // ── Status ─────────────────────────────────────────────────
  getStatus() {
    return {
      haConfigured: !!this.config.token,
      haUrl: this.config.baseUrl,
      devicesRegistered: this.devices.size,
      scenesRegistered: this.scenes.size,
    };
  }
}

module.exports = { KivoHome };
