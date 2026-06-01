import { execSync, exec } from 'child_process';
import fs from 'fs';
import path from 'path';
import os from 'os';

class StorageManager {
  constructor() {
    this.homeDir = os.homedir();
    this.downloadsDir = path.join(this.homeDir, 'Downloads');
    this.desktopDir = path.join(this.homeDir, 'Desktop');
    this.documentsDir = path.join(this.homeDir, 'Documents');
    this.internalStorageProtected = true;
    this.logFile = '/tmp/storage-manager.log';
    
    // File type categories for sorting
    this.categories = {
      images: ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico', '.tiff', '.heic'],
      videos: ['.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.webm', '.m4v', '.3gp'],
      audio: ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.aiff'],
      documents: ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.rtf', '.odt', '.ods', '.odp'],
      archives: ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'],
      code: ['.js', '.py', '.java', '.cpp', '.c', '.h', '.html', '.css', '.json', '.xml', '.ts', '.tsx', '.jsx'],
      installers: ['.dmg', '.pkg', '.app', '.exe', '.msi'],
      torrents: ['.torrent']
    };
    
    // Unnecessary file patterns to delete
    this.unnecessaryPatterns = [
      '*.tmp',
      '*.temp',
      '*.cache',
      '*.log',
      '*.old',
      '*.bak',
      '*.swp',
      '*~',
      '.DS_Store',
      'Thumbs.db',
      '.Spotlight-V100',
      '.Trashes',
      '.fseventsd',
      '.TemporaryItems'
    ];
  }

  log(level, message) {
    const timestamp = new Date().toISOString();
    const line = `[${timestamp}] [${level.toUpperCase()}] ${message}\n`;
    // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // console.debug(line.trim());
    try {
      fs.appendFileSync(this.logFile, line);
    } catch (e) {}
  }

  async getAllStorageLocations() {
    const locations = {
      internal: [],
      external: [],
      cloud: []
    };

    try {
      // Get all mounted volumes
      const output = execSync('df -H', { encoding: 'utf8' });
      const lines = output.trim().split('\n').slice(1);
      
      for (const line of lines) {
        const parts = line.split(/\s+/);
        if (parts.length >= 6) {
          const mountpoint = parts[5];
          const filesystem = parts[0];
          
          if (mountpoint === '/') {
            locations.internal.push({ mountpoint, filesystem, type: 'internal' });
          } else if (!mountpoint.startsWith('/System') && !mountpoint.startsWith('/private')) {
            locations.external.push({ mountpoint, filesystem, type: 'external' });
          }
        }
      }
    } catch (e) {
      this.log('error', `Failed to get storage locations: ${e.message}`);
    }

    // Check cloud storage directories
    const cloudDirs = [
      path.join(this.homeDir, 'Google Drive'),
      path.join(this.homeDir, 'Dropbox'),
      path.join(this.homeDir, 'OneDrive'),
      path.join(this.homeDir, 'Library', 'Mobile Documents', 'com~apple~CloudDocs')
    ];

    for (const dir of cloudDirs) {
      if (fs.existsSync(dir)) {
        locations.cloud.push({ mountpoint: dir, type: 'cloud' });
      }
    }

    return locations;
  }

  async sortDownloads() {
    this.log('info', 'Starting downloads sorting...');
    
    if (!fs.existsSync(this.downloadsDir)) {
      this.log('warn', 'Downloads directory not found');
      return;
    }

    const files = fs.readdirSync(this.downloadsDir);
    let movedCount = 0;

    for (const file of files) {
      const filePath = path.join(this.downloadsDir, file);
      const stat = fs.statSync(filePath);
      
      if (stat.isDirectory()) continue;

      const ext = path.extname(file).toLowerCase();
      let category = null;

      for (const [cat, extensions] of Object.entries(this.categories)) {
        if (extensions.includes(ext)) {
          category = cat;
          break;
        }
      }

      if (category) {
        const categoryDir = path.join(this.downloadsDir, category.toUpperCase());
        
        if (!fs.existsSync(categoryDir)) {
          fs.mkdirSync(categoryDir, { recursive: true });
        }

        const destPath = path.join(categoryDir, file);
        
        if (!fs.existsSync(destPath)) {
          fs.renameSync(filePath, destPath);
          movedCount++;
          this.log('info', `Moved ${file} to ${category.toUpperCase()}/`);
        }
      }
    }

    this.log('info', `Downloads sorting completed. Moved ${movedCount} files.`);
  }

  async cleanupDesktop() {
    this.log('info', 'Starting desktop cleanup...');
    
    if (!fs.existsSync(this.desktopDir)) {
      this.log('warn', 'Desktop directory not found');
      return;
    }

    const files = fs.readdirSync(this.desktopDir);
    let cleanedCount = 0;

    for (const file of files) {
      const filePath = path.join(this.desktopDir, file);
      const stat = fs.statSync(filePath);

      // Remove unnecessary files
      for (const pattern of this.unnecessaryPatterns) {
        if (this.matchesPattern(file, pattern)) {
          try {
            if (stat.isDirectory()) {
              fs.rmSync(filePath, { recursive: true, force: true });
            } else {
              fs.unlinkSync(filePath);
            }
            cleanedCount++;
            this.log('info', `Deleted ${file} from desktop`);
          } catch (e) {
            this.log('error', `Failed to delete ${file}: ${e.message}`);
          }
          break;
        }
      }

      // Move screenshots to Screenshots folder
      if (file.startsWith('Screenshot') || file.startsWith('Bildschirmfoto')) {
        const screenshotsDir = path.join(this.desktopDir, 'Screenshots');
        if (!fs.existsSync(screenshotsDir)) {
          fs.mkdirSync(screenshotsDir, { recursive: true });
        }
        const destPath = path.join(screenshotsDir, file);
        try {
          if (!fs.existsSync(destPath)) {
            fs.renameSync(filePath, destPath);
            cleanedCount++;
            this.log('info', `Moved ${file} to Screenshots/`);
          }
        } catch (e) {
          this.log('warn', `Could not move ${file}: ${e.message}`);
        }
      }

      // Move images to Images folder
      const ext = path.extname(file).toLowerCase();
      if (this.categories.images.includes(ext)) {
        const imagesDir = path.join(this.desktopDir, 'Images');
        if (!fs.existsSync(imagesDir)) {
          fs.mkdirSync(imagesDir, { recursive: true });
        }
        const destPath = path.join(imagesDir, file);
        try {
          if (!fs.existsSync(destPath)) {
            fs.renameSync(filePath, destPath);
            cleanedCount++;
            this.log('info', `Moved ${file} to Images/`);
          }
        } catch (e) {
          this.log('warn', `Could not move ${file}: ${e.message}`);
        }
      }
    }

    this.log('info', `Desktop cleanup completed. Cleaned ${cleanedCount} items.`);
  }

  matchesPattern(filename, pattern) {
    const regex = pattern.replace(/\*/g, '.*').replace(/\?/g, '.');
    return new RegExp(regex).test(filename);
  }

  async deleteUnnecessaryFiles(directory) {
    this.log('info', `Deleting unnecessary files in ${directory}...`);
    
    if (!fs.existsSync(directory)) {
      return;
    }

    let deletedCount = 0;

    const deleteRecursive = (dir) => {
      const files = fs.readdirSync(dir);
      
      for (const file of files) {
        const filePath = path.join(dir, file);
        const stat = fs.statSync(filePath);

        if (stat.isDirectory()) {
          // Check if directory is unnecessary
          if (this.unnecessaryPatterns.includes(file)) {
            try {
              fs.rmSync(filePath, { recursive: true, force: true });
              deletedCount++;
              this.log('info', `Deleted directory: ${filePath}`);
            } catch (e) {
              this.log('error', `Failed to delete directory ${filePath}: ${e.message}`);
            }
          } else {
            deleteRecursive(filePath);
          }
        } else {
          // Check if file is unnecessary
          for (const pattern of this.unnecessaryPatterns) {
            if (this.matchesPattern(file, pattern)) {
              try {
                fs.unlinkSync(filePath);
                deletedCount++;
                this.log('info', `Deleted file: ${filePath}`);
              } catch (e) {
                this.log('error', `Failed to delete file ${filePath}: ${e.message}`);
              }
              break;
            }
          }
        }
      }
    };

    deleteRecursive(directory);
    this.log('info', `Deleted ${deletedCount} unnecessary files from ${directory}`);
  }

  async protectInternalStorage() {
    this.log('info', 'Protecting internal storage...');
    
    // Create whitelist of necessary directories
    const necessaryDirs = [
      path.join(this.homeDir, 'Applications'),
      path.join(this.homeDir, 'Library'),
      path.join(this.homeDir, 'Documents'),
      path.join(this.homeDir, 'Desktop'),
      path.join(this.homeDir, 'Downloads'),
      path.join(this.homeDir, 'Pictures'),
      path.join(this.homeDir, 'Music'),
      path.join(this.homeDir, 'Movies'),
      '/System',
      '/Library',
      '/Applications'
    ];

    // Monitor internal storage usage
    try {
      const output = execSync('df -H /', { encoding: 'utf8' });
      const lines = output.trim().split('\n');
      const parts = lines[1].split(/\s+/);
      const usePercent = parseInt(parts[4]) || 0;

      if (usePercent > 90) {
        this.log('critical', `Internal storage at ${usePercent}%! Initiating emergency cleanup...`);
        await this.deleteUnnecessaryFiles(this.downloadsDir);
        await this.deleteUnnecessaryFiles(this.desktopDir);
        await this.deleteUnnecessaryFiles(path.join(this.homeDir, 'Library', 'Caches'));
      } else if (usePercent > 80) {
        this.log('warn', `Internal storage at ${usePercent}%`);
      }
    } catch (e) {
      this.log('error', `Failed to check internal storage: ${e.message}`);
    }
  }

  async organizeCloudStorage() {
    this.log('info', 'Organizing cloud storage...');
    
    const locations = await this.getAllStorageLocations();
    
    for (const cloud of locations.cloud) {
      this.log('info', `Processing cloud storage: ${cloud.mountpoint}`);
      
      // Sort files in cloud storage
      await this.sortDirectory(cloud.mountpoint);
      
      // Delete unnecessary files
      await this.deleteUnnecessaryFiles(cloud.mountpoint);
    }
  }

  async organizeExternalDrives() {
    this.log('info', 'Organizing external drives...');
    
    const locations = await this.getAllStorageLocations();
    
    for (const drive of locations.external) {
      this.log('info', `Processing external drive: ${drive.mountpoint}`);
      
      // Check disk usage
      try {
        const output = execSync(`df -H "${drive.mountpoint}"`, { encoding: 'utf8' });
        const lines = output.trim().split('\n');
        const parts = lines[1].split(/\s+/);
        const usePercent = parseInt(parts[4]) || 0;

        if (usePercent > 90) {
          this.log('critical', `External drive ${drive.mountpoint} at ${usePercent}%! Initiating cleanup...`);
          await this.deleteUnnecessaryFiles(drive.mountpoint);
        }
      } catch (e) {
        this.log('error', `Failed to check external drive ${drive.mountpoint}: ${e.message}`);
      }
      
      // Sort files
      await this.sortDirectory(drive.mountpoint);
    }
  }

  async sortDirectory(directory) {
    this.log('info', `Sorting directory: ${directory}`);
    
    if (!fs.existsSync(directory)) {
      return;
    }

    const files = fs.readdirSync(directory);
    let movedCount = 0;

    for (const file of files) {
      const filePath = path.join(directory, file);
      const stat = fs.statSync(filePath);
      
      if (stat.isDirectory()) continue;

      const ext = path.extname(file).toLowerCase();
      let category = null;

      for (const [cat, extensions] of Object.entries(this.categories)) {
        if (extensions.includes(ext)) {
          category = cat;
          break;
        }
      }

      if (category) {
        const categoryDir = path.join(directory, category.toUpperCase());
        
        if (!fs.existsSync(categoryDir)) {
          fs.mkdirSync(categoryDir, { recursive: true });
        }

        const destPath = path.join(categoryDir, file);
        
        if (!fs.existsSync(destPath)) {
          fs.renameSync(filePath, destPath);
          movedCount++;
          this.log('info', `Moved ${file} to ${category.toUpperCase()}/`);
        }
      }
    }

    this.log('info', `Directory sorting completed. Moved ${movedCount} files.`);
  }

  async runFullCleanup() {
    this.log('info', 'Starting full storage cleanup and organization...');
    
    // Sort downloads
    await this.sortDownloads();
    
    // Clean desktop
    await this.cleanupDesktop();
    
    // Protect internal storage
    await this.protectInternalStorage();
    
    // Organize cloud storage
    await this.organizeCloudStorage();
    
    // Organize external drives
    await this.organizeExternalDrives();
    
    this.log('info', 'Full storage cleanup and organization completed.');
  }

  async getStorageReport() {
    const locations = await this.getAllStorageLocations();
    const report = {
      timestamp: new Date().toISOString(),
      internal: [],
      external: [],
      cloud: []
    };

    for (const loc of locations.internal) {
      try {
        const output = execSync(`df -H "${loc.mountpoint}"`, { encoding: 'utf8' });
        const lines = output.trim().split('\n');
        const parts = lines[1].split(/\s+/);
        report.internal.push({
          mountpoint: loc.mountpoint,
          size: parts[1],
          used: parts[2],
          available: parts[3],
          usePercent: parseInt(parts[4]) || 0
        });
      } catch (e) {}
    }

    for (const loc of locations.external) {
      try {
        const output = execSync(`df -H "${loc.mountpoint}"`, { encoding: 'utf8' });
        const lines = output.trim().split('\n');
        const parts = lines[1].split(/\s+/);
        report.external.push({
          mountpoint: loc.mountpoint,
          size: parts[1],
          used: parts[2],
          available: parts[3],
          usePercent: parseInt(parts[4]) || 0
        });
      } catch (e) {}
    }

    for (const loc of locations.cloud) {
      report.cloud.push({
        mountpoint: loc.mountpoint,
        exists: fs.existsSync(loc.mountpoint)
      });
    }

    return report;
  }
}

export default StorageManager;
