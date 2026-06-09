import { AuthConfig, AuthAction } from './types.js';
import jwt from 'jsonwebtoken';

export class AuthController {
  private config: AuthConfig;

  constructor(config: AuthConfig) {
    this.config = config;
  }

  async execute(action: AuthAction): Promise<any> {
    switch (action.action) {
      case 'generateToken':
        return this.generateToken(action.payload);
      case 'verifyToken':
        return this.verifyToken(action.token!);
      case 'refreshToken':
        return this.refreshToken(action.token!);
      default:
        throw new Error(`Unknown auth action: ${action.action}`);
    }
  }

  private generateToken(payload: any): any {
    try {
      const expiresIn = this.config.expiresIn || '24h';
      const token = jwt.sign(payload, this.config.jwtSecret, { expiresIn: expiresIn as any });
      return { success: true, token, expiresIn };
    } catch (error: any) {
      throw new Error(`Token generation failed: ${error.message}`);
    }
  }

  private verifyToken(token: string): any {
    try {
      const decoded = jwt.verify(token, this.config.jwtSecret);
      return { success: true, decoded };
    } catch (error: any) {
      throw new Error(`Token verification failed: ${error.message}`);
    }
  }

  private refreshToken(token: string): any {
    try {
      const decoded = jwt.verify(token, this.config.jwtSecret, { ignoreExpiration: true }) as any;
      const expiresIn = this.config.expiresIn || '24h';
      const newToken = jwt.sign(
        { ...decoded, iat: Math.floor(Date.now() / 1000) },
        this.config.jwtSecret,
        { expiresIn: expiresIn as any }
      );
      return { success: true, token: newToken };
    } catch (error: any) {
      throw new Error(`Token refresh failed: ${error.message}`);
    }
  }
}
