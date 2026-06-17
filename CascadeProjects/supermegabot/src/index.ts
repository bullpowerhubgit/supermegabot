import express from 'express';
import { createServer } from 'http';
import { Server as SocketIOServer } from 'socket.io';
import dotenv from 'dotenv';

import { SuperMegaBot } from './core/SuperMegaBot';
import { AgentOrchestrator } from './agents/AgentOrchestrator';
import { ShopifyIntegration } from './integrations/ShopifyIntegration';
import { TelegramBot } from './bots/TelegramBot';
import { Logger } from './utils/Logger';

dotenv.config();

const app = express();
const server = createServer(app);
const io = new SocketIOServer(server, {
  cors: {
    origin: process.env.CORS_ORIGIN || "*",
    methods: ["GET", "POST"]
  }
});

const logger = new Logger('SuperMegaBot');
const bot = new SuperMegaBot();
const orchestrator = new AgentOrchestrator();
const shopify = new ShopifyIntegration();
const telegram = new TelegramBot();

app.use(express.json());
app.use(express.static('public'));

// Health check
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    agents: orchestrator.getStatus(),
    shopify: shopify.isConnected(),
    telegram: telegram.isConnected()
  });
});

// API Routes
app.get('/api/status', (req, res) => {
  res.json({
    bot: bot.getStatus(),
    agents: orchestrator.getAgentStatus(),
    performance: bot.getPerformanceMetrics()
  });
});

app.post('/api/agents/:agentId/execute', async (req, res) => {
  try {
    const { agentId } = req.params;
    const { command, parameters } = req.body;
    
    const result = await orchestrator.executeAgent(agentId, command, parameters);
    res.json({ success: true, result });
  } catch (error) {
    logger.error('Agent execution failed:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// Socket.IO for real-time updates
io.on('connection', (socket) => {
  logger.info('Client connected:', socket.id);
  
  socket.on('subscribe:agents', () => {
    socket.join('agents');
    socket.emit('agents:update', orchestrator.getAgentStatus());
  });
  
  socket.on('subscribe:performance', () => {
    socket.join('performance');
    socket.emit('performance:update', bot.getPerformanceMetrics());
  });
  
  socket.on('disconnect', () => {
    logger.info('Client disconnected:', socket.id);
  });
});

const PORT = process.env.PORT || 3000;

async function startServer() {
  try {
    // Initialize components
    await bot.initialize();
    await orchestrator.initialize();
    await shopify.initialize();
    await telegram.initialize();
    
    // Start server
    server.listen(PORT, () => {
      logger.info(`Super Mega Bot started on port ${PORT}`);
      logger.info(`Dashboard: http://localhost:${PORT}`);
    });
    
    // Start periodic updates
    setInterval(() => {
      io.to('agents').emit('agents:update', orchestrator.getAgentStatus());
      io.to('performance').emit('performance:update', bot.getPerformanceMetrics());
    }, 5000);
    
  } catch (error) {
    logger.error('Failed to start server:', error);
    process.exit(1);
  }
}

// Graceful shutdown
process.on('SIGINT', async () => {
  logger.info('Shutting down gracefully...');
  await bot.shutdown();
  await orchestrator.shutdown();
  await shopify.shutdown();
  await telegram.shutdown();
  process.exit(0);
});

startServer();
