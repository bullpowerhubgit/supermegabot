import { AzureConfig, AzureAction } from './types.js';
import { BlobServiceClient } from '@azure/storage-blob';

export class AzureController {
  private config: AzureConfig;
  private blobServiceClient: BlobServiceClient;

  constructor(config: AzureConfig) {
    this.config = config;
    this.blobServiceClient = BlobServiceClient.fromConnectionString(config.connectionString);
  }

  async execute(action: AzureAction): Promise<any> {
    switch (action.action) {
      case 'listContainers':
        return this.listContainers();
      case 'listBlobs':
        return this.listBlobs(action.containerName!);
      case 'upload':
        return this.upload(action.containerName!, action.blobName!, action.data!);
      case 'download':
        return this.download(action.containerName!, action.blobName!);
      case 'delete':
        return this.delete(action.containerName!, action.blobName!);
      case 'getBlobUrl':
        return this.getBlobUrl(action.containerName!, action.blobName!);
      default:
        throw new Error(`Unknown Azure action: ${action.action}`);
    }
  }

  private async listContainers(): Promise<any> {
    try {
      const containers: any[] = [];
      for await (const container of this.blobServiceClient.listContainers()) {
        containers.push({ name: container.name });
      }
      return { success: true, containers };
    } catch (error: any) {
      throw new Error(`Azure listContainers failed: ${error.message}`);
    }
  }

  private async listBlobs(containerName: string): Promise<any> {
    try {
      const containerClient = this.blobServiceClient.getContainerClient(containerName);
      const blobs: any[] = [];
      for await (const blob of containerClient.listBlobsFlat()) {
        blobs.push({ name: blob.name, size: blob.properties.contentLength });
      }
      return { success: true, blobs };
    } catch (error: any) {
      throw new Error(`Azure listBlobs failed: ${error.message}`);
    }
  }

  private async upload(containerName: string, blobName: string, data: string): Promise<any> {
    try {
      const containerClient = this.blobServiceClient.getContainerClient(containerName);
      const blockBlobClient = containerClient.getBlockBlobClient(blobName);
      await blockBlobClient.upload(data, data.length);
      return { success: true, message: 'Blob uploaded' };
    } catch (error: any) {
      throw new Error(`Azure upload failed: ${error.message}`);
    }
  }

  private async download(containerName: string, blobName: string): Promise<any> {
    try {
      const containerClient = this.blobServiceClient.getContainerClient(containerName);
      const blockBlobClient = containerClient.getBlockBlobClient(blobName);
      const downloadBlockBlobResponse = await blockBlobClient.download();
      const downloaded = await streamToString(downloadBlockBlobResponse.readableStreamBody!);
      return { success: true, data: downloaded };
    } catch (error: any) {
      throw new Error(`Azure download failed: ${error.message}`);
    }
  }

  private async delete(containerName: string, blobName: string): Promise<any> {
    try {
      const containerClient = this.blobServiceClient.getContainerClient(containerName);
      const blockBlobClient = containerClient.getBlockBlobClient(blobName);
      await blockBlobClient.delete();
      return { success: true, message: 'Blob deleted' };
    } catch (error: any) {
      throw new Error(`Azure delete failed: ${error.message}`);
    }
  }

  private async getBlobUrl(containerName: string, blobName: string): Promise<any> {
    try {
      const containerClient = this.blobServiceClient.getContainerClient(containerName);
      const blockBlobClient = containerClient.getBlockBlobClient(blobName);
      const url = blockBlobClient.url;
      return { success: true, url };
    } catch (error: any) {
      throw new Error(`Azure getBlobUrl failed: ${error.message}`);
    }
  }
}

async function streamToString(readableStream: any): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: any[] = [];
    readableStream.on('data', (chunk: any) => chunks.push(chunk));
    readableStream.on('error', reject);
    readableStream.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
  });
}
