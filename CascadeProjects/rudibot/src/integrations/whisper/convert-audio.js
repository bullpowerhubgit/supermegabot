/**
 * Convert Audio — FFmpeg-based audio normalization
 * Converts OGG/Opus → WAV (16kHz mono) for Whisper
 */

const { execFile } = require('child_process');
const { promisify } = require('util');
const fs = require('fs');
const path = require('path');

const execFileAsync = promisify(execFile);

const TEMP_DIR = process.env.TEMP_DIR || '/tmp/kivo-voice';

function ensureDir(dir) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

class AudioConverter {
  constructor(options = {}) {
    this.config = {
      sampleRate: options.sampleRate || 16000,
      channels: options.channels || 1,
      ffmpegPath: options.ffmpegPath || 'ffmpeg',
      ...options
    };
    ensureDir(TEMP_DIR);
  }

  // ── OGG to WAV ────────────────────────────────────────────
  async oggToWav(inputPath, outputPath = null) {
    if (!outputPath) {
      outputPath = inputPath.replace(/\.[^.]+$/, '.wav');
    }

    const args = [
      '-y', // Overwrite output
      '-i', inputPath,
      '-ac', String(this.config.channels), // Mono
      '-ar', String(this.config.sampleRate), // 16kHz
      '-acodec', 'pcm_s16le', // 16-bit PCM
      '-f', 'wav',
      outputPath
    ];

    try {
      await execFileAsync(this.config.ffmpegPath, args, {
        timeout: 30000,
        maxBuffer: 1024 * 1024
      });

      const stats = fs.statSync(outputPath);
      return {
        success: true,
        inputPath,
        outputPath,
        size: stats.size,
        sampleRate: this.config.sampleRate,
        channels: this.config.channels
      };
    } catch (e) {
      // Cleanup failed output
      this.cleanup(outputPath);
      throw new Error(`FFmpeg conversion failed: ${e.message}`);
    }
  }

  // ── Generic Conversion ──────────────────────────────────────
  async convert(inputPath, outputFormat = 'wav', options = {}) {
    const ext = path.extname(inputPath);
    const base = inputPath.slice(0, -ext.length);
    const outputPath = options.outputPath || `${base}.${outputFormat}`;

    const formatArgs = this.getFormatArgs(outputFormat, options);

    const args = [
      '-y',
      '-i', inputPath,
      ...formatArgs,
      outputPath
    ];

    try {
      await execFileAsync(this.config.ffmpegPath, args, {
        timeout: 30000,
        maxBuffer: 1024 * 1024
      });

      return {
        success: true,
        inputPath,
        outputPath,
        format: outputFormat
      };
    } catch (e) {
      this.cleanup(outputPath);
      throw new Error(`Conversion failed: ${e.message}`);
    }
  }

  getFormatArgs(format, options) {
    switch (format) {
      case 'wav':
        return [
          '-ac', String(options.channels || this.config.channels),
          '-ar', String(options.sampleRate || this.config.sampleRate),
          '-acodec', 'pcm_s16le'
        ];
      case 'mp3':
        return [
          '-ac', '1',
          '-ar', '16000',
          '-b:a', '32k'
        ];
      case 'flac':
        return [
          '-ac', '1',
          '-ar', '16000',
          '-compression_level', '5'
        ];
      default:
        return [];
    }
  }

  // ── Audio Info ──────────────────────────────────────────────
  async getInfo(filePath) {
    const args = [
      '-v', 'quiet',
      '-print_format', 'json',
      '-show_format',
      '-show_streams',
      filePath
    ];

    try {
      const { stdout } = await execFileAsync('ffprobe', args, {
        timeout: 10000
      });

      const info = JSON.parse(stdout);
      const audioStream = info.streams.find(s => s.codec_type === 'audio');

      return {
        success: true,
        duration: parseFloat(info.format.duration) || 0,
        bitrate: parseInt(info.format.bit_rate) || 0,
        format: info.format.format_name,
        sampleRate: audioStream ? parseInt(audioStream.sample_rate) : null,
        channels: audioStream ? parseInt(audioStream.channels) : null,
        codec: audioStream ? audioStream.codec_name : null
      };
    } catch (e) {
      return {
        success: false,
        error: e.message
      };
    }
  }

  // ── Volume Normalization ────────────────────────────────────
  async normalize(inputPath, outputPath = null) {
    if (!outputPath) {
      outputPath = inputPath.replace(/\.[^.]+$/, '_normalized.wav');
    }

    const args = [
      '-y',
      '-i', inputPath,
      '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11',
      '-ac', '1',
      '-ar', '16000',
      '-acodec', 'pcm_s16le',
      outputPath
    ];

    try {
      await execFileAsync(this.config.ffmpegPath, args, { timeout: 30000 });
      return {
        success: true,
        inputPath,
        outputPath
      };
    } catch (e) {
      this.cleanup(outputPath);
      throw new Error(`Normalization failed: ${e.message}`);
    }
  }

  // ── Silence Trimming ────────────────────────────────────────
  async trimSilence(inputPath, outputPath = null) {
    if (!outputPath) {
      outputPath = inputPath.replace(/\.[^.]+$/, '_trimmed.wav');
    }

    const args = [
      '-y',
      '-i', inputPath,
      '-af', 'silenceremove=start_periods=1:start_duration=0.1:start_threshold=-50dB:detection=peak',
      '-ac', '1',
      '-ar', '16000',
      '-acodec', 'pcm_s16le',
      outputPath
    ];

    try {
      await execFileAsync(this.config.ffmpegPath, args, { timeout: 30000 });
      return {
        success: true,
        inputPath,
        outputPath
      };
    } catch (e) {
      this.cleanup(outputPath);
      throw new Error(`Silence trimming failed: ${e.message}`);
    }
  }

  // ── Cleanup ─────────────────────────────────────────────────
  cleanup(filePath) {
    try {
      if (fs.existsSync(filePath)) {
        fs.unlinkSync(filePath);
      }
    } catch (e) {
      console.warn(`[AudioConverter] Failed to cleanup: ${filePath}`, e.message);
    }
  }

  // ── Status ──────────────────────────────────────────────────
  getStatus() {
    return {
      ffmpegPath: this.config.ffmpegPath,
      sampleRate: this.config.sampleRate,
      channels: this.config.channels,
      tempDir: TEMP_DIR
    };
  }
}

module.exports = { AudioConverter };
