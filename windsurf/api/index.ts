import express from 'express';
import cors from 'cors';

const app = express();
app.use(cors());
app.use(express.json());

app.get('/', (_req, res) => {
  res.json({
    status: 'ok',
    service: 'RudiBot King of Tools',
    version: '3.0',
    timestamp: new Date().toISOString(),
    message: 'API läuft schlank - vollständige Orchestrator-Features auf localhost:3001',
    king_of_tools: {
      total_apis: 50,
      total_platforms: 48,
      total_agents: 8,
      total_micro_bots: 5
    }
  });
});

app.get('/api/health', (_req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

app.get('/api/orchestrator', (_req, res) => {
  res.json({
    status: 'ok',
    service: 'RudiBot Orchestrator',
    message: 'Für vollständige Features: Starte lokal mit `npm run dev` (Port 3001)',
    local_endpoints: {
      orchestrator: 'http://localhost:3001/api/orchestrator',
      health: 'http://localhost:3001/api/orchestrator/health',
      assistant: 'http://localhost:3001/api/assistant'
    }
  });
});

export default app;
