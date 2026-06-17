import { GoogleDriveConfig, GoogleDriveAction, GoogleAnalyticsConfig, GoogleAnalyticsAction } from './types.js';
import { google } from 'googleapis';
import { BetaAnalyticsDataClient } from '@google-analytics/data';

export class GoogleController {
  private driveConfig?: GoogleDriveConfig;
  private analyticsConfig?: GoogleAnalyticsConfig;
  private drive?: any;
  private analyticsData?: BetaAnalyticsDataClient;

  constructor(driveConfig?: GoogleDriveConfig, analyticsConfig?: GoogleAnalyticsConfig) {
    this.driveConfig = driveConfig;
    this.analyticsConfig = analyticsConfig;

    if (driveConfig) {
      const auth = new google.auth.GoogleAuth({
        credentials: driveConfig.credentials,
        scopes: ['https://www.googleapis.com/auth/drive'],
      });
      this.drive = google.drive({ version: 'v3', auth });
    }

    if (analyticsConfig) {
      this.analyticsData = new BetaAnalyticsDataClient({
        credentials: analyticsConfig.credentials,
      });
    }
  }

  async executeDrive(action: GoogleDriveAction): Promise<any> {
    if (!this.drive) {
      throw new Error('Drive not configured');
    }

    switch (action.action) {
      case 'listFiles':
        return this.listFiles(action.folderId);
      case 'getFile':
        return this.getFile(action.fileId!);
      case 'uploadFile':
        return this.uploadFile(action.data, action.folderId);
      case 'downloadFile':
        return this.downloadFile(action.fileId!);
      case 'deleteFile':
        return this.deleteFile(action.fileId!);
      case 'createFolder':
        return this.createFolder(action.data, action.folderId);
      default:
        throw new Error(`Unknown Google Drive action: ${action.action}`);
    }
  }

  async executeAnalytics(action: GoogleAnalyticsAction): Promise<any> {
    if (!this.analyticsData) {
      throw new Error('Analytics not configured');
    }

    switch (action.action) {
      case 'getReports':
        return this.getReports(action.propertyId!, action.dateRange, action.metrics, action.dimensions);
      case 'getRealtime':
        return this.getRealtime(action.propertyId!);
      case 'getEvents':
        return this.getEvents(action.propertyId!, action.dateRange);
      case 'getUsers':
        return this.getUsers(action.propertyId!, action.dateRange);
      default:
        throw new Error(`Unknown Google Analytics action: ${action.action}`);
    }
  }

  private async listFiles(folderId?: string): Promise<any> {
    try {
      const query = folderId ? `'${folderId}' in parents` : undefined;
      const response = await this.drive.files.list({
        q: query,
        fields: 'files(id, name, mimeType, size)',
      });
      return { success: true, files: response.data.files };
    } catch (error: any) {
      throw new Error(`Google Drive listFiles failed: ${error.message}`);
    }
  }

  private async getFile(fileId: string): Promise<any> {
    try {
      const response = await this.drive.files.get({
        fileId,
        fields: 'id, name, mimeType, size',
      });
      return { success: true, file: response.data };
    } catch (error: any) {
      throw new Error(`Google Drive getFile failed: ${error.message}`);
    }
  }

  private async uploadFile(data: any, folderId?: string): Promise<any> {
    try {
      const media = {
        mimeType: data.mimeType,
        body: data.body,
      };
      const response = await this.drive.files.create({
        requestBody: {
          name: data.name,
          parents: folderId ? [folderId] : undefined,
        },
        media,
      });
      return { success: true, file: response.data };
    } catch (error: any) {
      throw new Error(`Google Drive uploadFile failed: ${error.message}`);
    }
  }

  private async downloadFile(fileId: string): Promise<any> {
    try {
      const response = await this.drive.files.get({
        fileId,
        alt: 'media',
      });
      return { success: true, data: response.data };
    } catch (error: any) {
      throw new Error(`Google Drive downloadFile failed: ${error.message}`);
    }
  }

  private async deleteFile(fileId: string): Promise<any> {
    try {
      await this.drive.files.delete({ fileId });
      return { success: true, message: 'File deleted' };
    } catch (error: any) {
      throw new Error(`Google Drive deleteFile failed: ${error.message}`);
    }
  }

  private async createFolder(data: any, folderId?: string): Promise<any> {
    try {
      const response = await this.drive.files.create({
        requestBody: {
          name: data.name,
          mimeType: 'application/vnd.google-apps.folder',
          parents: folderId ? [folderId] : undefined,
        },
      });
      return { success: true, folder: response.data };
    } catch (error: any) {
      throw new Error(`Google Drive createFolder failed: ${error.message}`);
    }
  }

  private async getReports(propertyId: string, dateRange?: string, metrics?: string[], dimensions?: string[]): Promise<any> {
    try {
      const response = await this.analyticsData!.runReport({
        property: `properties/${propertyId}`,
        dateRanges: [{ startDate: dateRange || '30daysAgo', endDate: 'today' }],
        metrics: metrics?.map(m => ({ name: m })) || [{ name: 'activeUsers' }],
        dimensions: dimensions?.map(d => ({ name: d })),
      });
      return { success: true, reports: response && response[0] ? response[0] : response };
    } catch (error: any) {
      throw new Error(`Google Analytics getReports failed: ${error.message}`);
    }
  }

  private async getRealtime(propertyId: string): Promise<any> {
    try {
      const response = await this.analyticsData!.runRealtimeReport({
        property: `properties/${propertyId}`,
        metrics: [{ name: 'activeUsers' }],
      });
      return { success: true, realtime: response && response[0] ? response[0] : response };
    } catch (error: any) {
      throw new Error(`Google Analytics getRealtime failed: ${error.message}`);
    }
  }

  private async getEvents(propertyId: string, dateRange?: string): Promise<any> {
    try {
      const response = await this.analyticsData!.runReport({
        property: `properties/${propertyId}`,
        dateRanges: [{ startDate: dateRange || '30daysAgo', endDate: 'today' }],
        metrics: [{ name: 'eventCount' }],
        dimensions: [{ name: 'eventName' }],
      });
      return { success: true, events: response && response[0] ? response[0] : response };
    } catch (error: any) {
      throw new Error(`Google Analytics getEvents failed: ${error.message}`);
    }
  }

  private async getUsers(propertyId: string, dateRange?: string): Promise<any> {
    try {
      const response = await this.analyticsData!.runReport({
        property: `properties/${propertyId}`,
        dateRanges: [{ startDate: dateRange || '30daysAgo', endDate: 'today' }],
        metrics: [{ name: 'totalUsers' }, { name: 'activeUsers' }],
      });
      return { success: true, users: response && response[0] ? response[0] : response };
    } catch (error: any) {
      throw new Error(`Google Analytics getUsers failed: ${error.message}`);
    }
  }
}
