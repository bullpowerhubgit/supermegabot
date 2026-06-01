/**
 * Claude API Proxy Route
 * Proxies requests to Anthropic API to avoid exposing API keys in frontend
 */

import express from 'express';
import axios from 'axios';

const router = express.Router();

router.post('/', async (req, res) => {
  try {
    const { model, max_tokens, messages } = req.body;
    
    if (!messages || !Array.isArray(messages) || messages.length === 0) {
      return res.status(400).json({ error: 'Invalid messages format' });
    }

    const apiKey = process.env.ANTHROPIC_API_KEY;
    
    if (!apiKey) {
      return res.status(500).json({ 
        error: 'ANTHROPIC_API_KEY not configured in environment' 
      });
    }

    const response = await axios.post(
      'https://api.anthropic.com/v1/messages',
      {
        model: model || 'claude-sonnet-4-20250514',
        max_tokens: max_tokens || 1200,
        messages: messages
      },
      {
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': apiKey,
          'anthropic-version': '2023-06-01'
        }
      }
    );

    res.status(response.status).json(response.data);
    
  } catch (error) {
    console.error('Claude API Error:', error.response?.data || error.message);
    
    if (error.response) {
      res.status(error.response.status).json(error.response.data);
    } else {
      res.status(500).json({ 
        error: 'Failed to connect to Claude API',
        message: error.message 
      });
    }
  }
});

export default router;
