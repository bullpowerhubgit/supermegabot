/**
 * RUDIBOT JWT Authentication & Authorization Middleware
 * Production-ready auth system with user management
 */

const jwt = require('jsonwebtoken');
const crypto = require('crypto');

// In-memory user store (replace with Supabase/DB in production)
const users = new Map();
const refreshTokens = new Set();

// JWT Secret (use strong secret in production)
const JWT_SECRET = process.env.JWT_SECRET || crypto.randomBytes(64).toString('hex');
const JWT_REFRESH_SECRET = process.env.JWT_REFRESH_SECRET || crypto.randomBytes(64).toString('hex');

// Default admin user
const ADMIN_USER = {
  id: 'admin-001',
  email: 'admin@rudibot.com',
  password: process.env.ADMIN_PASSWORD || 'RudiBot2025!',
  role: 'admin',
  plan: 'agency',
  createdAt: new Date().toISOString(),
  lastLogin: null,
  isActive: true,
  permissions: ['all']
};

// Initialize admin
users.set(ADMIN_USER.email, ADMIN_USER);

class AuthSystem {
  constructor() {
    this.logger = console;
  }

  // Generate JWT Token
  generateTokens(user) {
    const accessToken = jwt.sign(
      { 
        userId: user.id, 
        email: user.email, 
        role: user.role,
        plan: user.plan,
        permissions: user.permissions
      },
      JWT_SECRET,
      { expiresIn: '15m' }
    );

    const refreshToken = jwt.sign(
      { userId: user.id },
      JWT_REFRESH_SECRET,
      { expiresIn: '7d' }
    );

    refreshTokens.add(refreshToken);
    return { accessToken, refreshToken };
  }

  // Middleware: Authenticate JWT
  authenticate(req, res, next) {
    const authHeader = req.headers['authorization'];
    const token = authHeader && authHeader.split(' ')[1]; // Bearer TOKEN

    if (!token) {
      return res.status(401).json({ 
        success: false, 
        error: 'Access token required',
        code: 'NO_TOKEN'
      });
    }

    try {
      const decoded = jwt.verify(token, JWT_SECRET);
      req.user = decoded;
      next();
    } catch (error) {
      if (error.name === 'TokenExpiredError') {
        return res.status(401).json({ 
          success: false, 
          error: 'Token expired',
          code: 'TOKEN_EXPIRED'
        });
      }
      return res.status(403).json({ 
        success: false, 
        error: 'Invalid token',
        code: 'INVALID_TOKEN'
      });
    }
  }

  // Middleware: Check Role
  requireRole(...roles) {
    return (req, res, next) => {
      if (!req.user) {
        return res.status(401).json({ 
          success: false, 
          error: 'Authentication required' 
        });
      }

      if (!roles.includes(req.user.role)) {
        return res.status(403).json({ 
          success: false, 
          error: `Required role: ${roles.join(' or ')}`,
          code: 'INSUFFICIENT_ROLE'
        });
      }

      next();
    };
  }

  // Middleware: Check Plan
  requirePlan(...plans) {
    return (req, res, next) => {
      if (!req.user) {
        return res.status(401).json({ 
          success: false, 
          error: 'Authentication required' 
        });
      }

      if (!plans.includes(req.user.plan)) {
        return res.status(403).json({ 
          success: false, 
          error: `Required plan: ${plans.join(' or ')}`,
          code: 'PLAN_UPGRADE_REQUIRED',
          upgradeUrl: '/api/billing/upgrade'
        });
      }

      next();
    };
  }

  // Login Handler
  async login(req, res) {
    const { email, password } = req.body;

    if (!email || !password) {
      return res.status(400).json({ 
        success: false, 
        error: 'Email and password required' 
      });
    }

    const user = users.get(email);
    
    if (!user || !user.isActive) {
      return res.status(401).json({ 
        success: false, 
        error: 'Invalid credentials',
        code: 'INVALID_CREDENTIALS'
      });
    }

    if (user.password !== password) {
      return res.status(401).json({ 
        success: false, 
        error: 'Invalid credentials',
        code: 'INVALID_CREDENTIALS'
      });
    }

    // Update last login
    user.lastLogin = new Date().toISOString();

    const tokens = this.generateTokens(user);

    res.json({
      success: true,
      user: {
        id: user.id,
        email: user.email,
        role: user.role,
        plan: user.plan,
        permissions: user.permissions
      },
      ...tokens
    });
  }

  // Register Handler
  async register(req, res) {
    const { email, password, plan = 'starter' } = req.body;

    if (!email || !password) {
      return res.status(400).json({ 
        success: false, 
        error: 'Email and password required' 
      });
    }

    if (users.has(email)) {
      return res.status(409).json({ 
        success: false, 
        error: 'User already exists',
        code: 'USER_EXISTS'
      });
    }

    const newUser = {
      id: `user-${Date.now()}`,
      email,
      password,
      role: 'user',
      plan,
      createdAt: new Date().toISOString(),
      lastLogin: null,
      isActive: true,
      permissions: plan === 'starter' ? ['read', 'basic_automation'] :
                   plan === 'pro' ? ['read', 'write', 'advanced_automation', 'analytics'] :
                   ['all']
    };

    users.set(email, newUser);

    const tokens = this.generateTokens(newUser);

    res.status(201).json({
      success: true,
      message: 'User registered successfully',
      user: {
        id: newUser.id,
        email: newUser.email,
        role: newUser.role,
        plan: newUser.plan
      },
      ...tokens
    });
  }

  // Refresh Token Handler
  async refresh(req, res) {
    const { refreshToken } = req.body;

    if (!refreshToken || !refreshTokens.has(refreshToken)) {
      return res.status(403).json({ 
        success: false, 
        error: 'Invalid refresh token' 
      });
    }

    try {
      const decoded = jwt.verify(refreshToken, JWT_REFRESH_SECRET);
      const user = Array.from(users.values()).find(u => u.id === decoded.userId);

      if (!user || !user.isActive) {
        return res.status(403).json({ 
          success: false, 
          error: 'User not found or inactive' 
        });
      }

      const tokens = this.generateTokens(user);
      refreshTokens.delete(refreshToken); // One-time use

      res.json({
        success: true,
        ...tokens
      });
    } catch (error) {
      return res.status(403).json({ 
        success: false, 
        error: 'Invalid refresh token' 
      });
    }
  }

  // Logout Handler
  async logout(req, res) {
    const { refreshToken } = req.body;
    
    if (refreshToken) {
      refreshTokens.delete(refreshToken);
    }

    res.json({
      success: true,
      message: 'Logged out successfully'
    });
  }

  // Get Current User
  async me(req, res) {
    const user = Array.from(users.values()).find(u => u.id === req.user.userId);
    
    if (!user) {
      return res.status(404).json({ 
        success: false, 
        error: 'User not found' 
      });
    }

    res.json({
      success: true,
      user: {
        id: user.id,
        email: user.email,
        role: user.role,
        plan: user.plan,
        permissions: user.permissions,
        createdAt: user.createdAt,
        lastLogin: user.lastLogin
      }
    });
  }

  // Get User by ID (admin only)
  getUserById(userId) {
    return Array.from(users.values()).find(u => u.id === userId);
  }

  // List all users (admin only)
  listUsers() {
    return Array.from(users.values()).map(u => ({
      id: u.id,
      email: u.email,
      role: u.role,
      plan: u.plan,
      isActive: u.isActive,
      createdAt: u.createdAt,
      lastLogin: u.lastLogin
    }));
  }

  // Express Router
  getRouter() {
    const express = require('express');
    const router = express.Router();

    // Public routes
    router.post('/login', (req, res) => this.login(req, res));
    router.post('/register', (req, res) => this.register(req, res));
    router.post('/refresh', (req, res) => this.refresh(req, res));

    // Protected routes
    router.post('/logout', this.authenticate.bind(this), (req, res) => this.logout(req, res));
    router.get('/me', this.authenticate.bind(this), (req, res) => this.me(req, res));

    // Admin routes
    router.get('/users', 
      this.authenticate.bind(this),
      this.requireRole('admin').bind(this),
      (req, res) => {
        res.json({
          success: true,
          users: this.listUsers()
        });
      }
    );

    return router;
  }
}

module.exports = { AuthSystem, JWT_SECRET };
