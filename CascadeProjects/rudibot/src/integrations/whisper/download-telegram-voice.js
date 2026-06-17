/**
 * Download Telegram Voice — Downloads voice messages from Telegram
 * Handles file_id → local file path conversion
 */

const fs = require('fs');
const path = require('path');
const { pipeline } = require('stream/promises');

const TEMP_DIR = process.env.TEMP_DIR || '/tmp/kivo-voice';

function ensureDir(dir) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

class TelegramVoiceDownloader {
  constructor(bot) {
    this.bot = bot;
    ensureDir(TEMP_DIR);
  }

  async download(voiceMessage) {
    const { file_id, duration, mime_type } = voiceMessage;
    
    try {
      // Get file path from Telegram
      const file = await this.bot.getFile(file_id);
      const fileUrl = await this.bot.getFileLink(file_id);
      
      // Download file
      const extension = this.getExtension(mime_type);
      const localPath = path.join(TEMP_DIR, `voice_${Date.now()}.${extension}`);
      
      const response = await fetch(fileUrl);
      if (!response.ok) {
        throw new Error(`Download failed: ${response.status} ${response.statusText}`);
      }
      
      const fileStream = fs.createWriteStream(localPath);
      await pipeline(response.body, fileStream);
      
      const stats = fs.statSync(localPath);
      
      return {
        success: true,
        path: localPath,
        duration: duration || 0,
        mimeType: mime_type,
        size: stats.size,
        fileId: file_id
      };
      
    } catch (e) {
      return {
        success: false,
        error: e.message,
        fileId: file_id
      };
    }
  }

  getExtension(mimeType) {
    const map = {
      'audio/ogg': 'ogg',
      'audio/opus': 'ogg',
      'audio/mpeg': 'mp3',
      'audio/mp4': 'm4a',
      'audio/wav': 'wav',
      'audio/x-wav': 'wav'
    };
    return map[mimeType] || 'ogg';
  }

  // ── Batch Download ─────────────────────────────────────────
  async downloadBatch(voiceMessages) {
    const results = [];
    for (const msg of voiceMessages) {
      const result = await this.download(msg);
      results.push(result);
    }
    return results;
  }

  // ── Cleanup ────────────────────────────────────────────────
  cleanup(filePath) {
    try {
      if (fs.existsSync(filePath)) {
        fs.unlinkSync(filePath);
      }
    } catch (e) {
      console.warn(`[VoiceDownloader] Failed to cleanup: ${filePath}`, e.message);
    }
  }

  cleanupOld(maxAge = 3600000) { // 1 hour
    try {
      const files = fs.readdirSync(TEMP_DIR);
      const now = Date.now();
      
      for (const file of files) {
        const filePath = path.join(TEMP_DIR, file);
        const stats = fs.statSync(filePath);
        if (now - stats.mtime.getTime() > maxAge) {
          this.cleanup(filePath);
        }
      }
    } catch (e) {
      console.warn('[VoiceDownloader] Cleanup error:', e.message);
    }
  }

  // ── Status ─────────────────────────────────────────────────
  getStatus() {
    return {
      tempDir: TEMP_DIR,
      botConfigured: !!this.bot
    };
  }
}

module.exports = { TelegramVoiceDownloader };
