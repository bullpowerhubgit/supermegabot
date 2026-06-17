import { AWSConfig, S3Action, LambdaAction } from './types.js';
import { S3Client, ListBucketsCommand, ListObjectsV2Command, PutObjectCommand, GetObjectCommand, DeleteObjectCommand } from '@aws-sdk/client-s3';
import { LambdaClient, ListFunctionsCommand, GetFunctionCommand, InvokeCommand, CreateFunctionCommand, UpdateFunctionCodeCommand, DeleteFunctionCommand } from '@aws-sdk/client-lambda';

export class AWSController {
  private config: AWSConfig;
  private s3Client: S3Client;
  private lambdaClient: LambdaClient;

  constructor(config: AWSConfig) {
    this.config = config;
    this.s3Client = new S3Client({
      credentials: {
        accessKeyId: config.accessKeyId,
        secretAccessKey: config.secretAccessKey,
      },
      region: config.region || 'us-east-1',
    });
    this.lambdaClient = new LambdaClient({
      credentials: {
        accessKeyId: config.accessKeyId,
        secretAccessKey: config.secretAccessKey,
      },
      region: config.region || 'us-east-1',
    });
  }

  async executeS3(action: S3Action): Promise<any> {
    switch (action.action) {
      case 'listBuckets':
        return this.listBuckets();
      case 'listObjects':
        return this.listObjects(action.bucket!);
      case 'upload':
        return this.upload(action.bucket!, action.key!, action.data!);
      case 'download':
        return this.download(action.bucket!, action.key!);
      case 'delete':
        return this.delete(action.bucket!, action.key!);
      case 'getPresignedUrl':
        return this.getPresignedUrl(action.bucket!, action.key!, action.expiresIn);
      default:
        throw new Error(`Unknown S3 action: ${action.action}`);
    }
  }

  async executeLambda(action: LambdaAction): Promise<any> {
    switch (action.action) {
      case 'listFunctions':
        return this.listFunctions();
      case 'getFunction':
        return this.getFunction(action.functionName!);
      case 'invokeFunction':
        return this.invokeFunction(action.functionName!, action.payload);
      case 'createFunction':
        return this.createFunction(action.data);
      case 'updateFunction':
        return this.updateFunction(action.functionName!, action.data);
      case 'deleteFunction':
        return this.deleteFunction(action.functionName!);
      default:
        throw new Error(`Unknown Lambda action: ${action.action}`);
    }
  }

  private async listBuckets(): Promise<any> {
    try {
      const command = new ListBucketsCommand({});
      const response = await this.s3Client.send(command);
      return { success: true, buckets: response.Buckets };
    } catch (error: any) {
      throw new Error(`S3 listBuckets failed: ${error.message}`);
    }
  }

  private async listObjects(bucket: string): Promise<any> {
    try {
      const command = new ListObjectsV2Command({ Bucket: bucket });
      const response = await this.s3Client.send(command);
      return { success: true, objects: response.Contents };
    } catch (error: any) {
      throw new Error(`S3 listObjects failed: ${error.message}`);
    }
  }

  private async upload(bucket: string, key: string, data: string): Promise<any> {
    try {
      const command = new PutObjectCommand({
        Bucket: bucket,
        Key: key,
        Body: data,
      });
      await this.s3Client.send(command);
      return { success: true, message: 'File uploaded' };
    } catch (error: any) {
      throw new Error(`S3 upload failed: ${error.message}`);
    }
  }

  private async download(bucket: string, key: string): Promise<any> {
    try {
      const command = new GetObjectCommand({ Bucket: bucket, Key: key });
      const response = await this.s3Client.send(command);
      const str = await response.Body?.transformToString();
      return { success: true, data: str };
    } catch (error: any) {
      throw new Error(`S3 download failed: ${error.message}`);
    }
  }

  private async delete(bucket: string, key: string): Promise<any> {
    try {
      const command = new DeleteObjectCommand({ Bucket: bucket, Key: key });
      await this.s3Client.send(command);
      return { success: true, message: 'File deleted' };
    } catch (error: any) {
      throw new Error(`S3 delete failed: ${error.message}`);
    }
  }

  private async getPresignedUrl(bucket: string, key: string, expiresIn?: number): Promise<any> {
    try {
      // Note: Presigned URLs require additional setup with @aws-sdk/s3-request-presigner
      return { success: true, message: 'Presigned URL requires additional setup' };
    } catch (error: any) {
      throw new Error(`S3 getPresignedUrl failed: ${error.message}`);
    }
  }

  private async listFunctions(): Promise<any> {
    try {
      const command = new ListFunctionsCommand({});
      const response = await this.lambdaClient.send(command);
      return { success: true, functions: response.Functions };
    } catch (error: any) {
      throw new Error(`Lambda listFunctions failed: ${error.message}`);
    }
  }

  private async getFunction(functionName: string): Promise<any> {
    try {
      const command = new GetFunctionCommand({ FunctionName: functionName });
      const response = await this.lambdaClient.send(command);
      return { success: true, function: response.Configuration };
    } catch (error: any) {
      throw new Error(`Lambda getFunction failed: ${error.message}`);
    }
  }

  private async invokeFunction(functionName: string, payload?: any): Promise<any> {
    try {
      const command = new InvokeCommand({
        FunctionName: functionName,
        Payload: JSON.stringify(payload || {}),
      });
      const response = await this.lambdaClient.send(command);
      return { success: true, result: JSON.parse(new TextDecoder().decode(response.Payload!)) };
    } catch (error: any) {
      throw new Error(`Lambda invokeFunction failed: ${error.message}`);
    }
  }

  private async createFunction(data: any): Promise<any> {
    try {
      const command = new CreateFunctionCommand(data);
      const response = await this.lambdaClient.send(command);
      return { success: true, function: response };
    } catch (error: any) {
      throw new Error(`Lambda createFunction failed: ${error.message}`);
    }
  }

  private async updateFunction(functionName: string, data: any): Promise<any> {
    try {
      const command = new UpdateFunctionCodeCommand({
        FunctionName: functionName,
        ZipFile: data.zipFile,
      });
      const response = await this.lambdaClient.send(command);
      return { success: true, function: response };
    } catch (error: any) {
      throw new Error(`Lambda updateFunction failed: ${error.message}`);
    }
  }

  private async deleteFunction(functionName: string): Promise<any> {
    try {
      const command = new DeleteFunctionCommand({ FunctionName: functionName });
      await this.lambdaClient.send(command);
      return { success: true, message: 'Function deleted' };
    } catch (error: any) {
      throw new Error(`Lambda deleteFunction failed: ${error.message}`);
    }
  }
}
