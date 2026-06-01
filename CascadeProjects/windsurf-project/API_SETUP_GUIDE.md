# API Integration Setup Guide

## Overview
This guide explains how to configure the real API data integration for the Quick Cash System and High-Ticket Dashboard.

## Prerequisites

### 1. Install Dependencies
```bash
npm install next react react-dom lucide-react
npm install -D typescript @types/react @types/node
```

### 2. Anthropic API Key
You need an Anthropic API key to use Claude AI features:
1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Sign up or log in
3. Create an API key
4. Copy the key (starts with `sk-ant-`)

## Configuration

### Environment Variables
Edit `.env.local` file in the project root:

```env
# Anthropic API Configuration
ANTHROPIC_API_KEY=sk-ant-your-actual-api-key-here

# App Configuration
NEXT_PUBLIC_APP_URL=http://localhost:3000
```

**Important:** Replace `sk-ant-your-actual-api-key-here` with your real Anthropic API key.

## Project Structure

```
windsurf-project/
├── pages/
│   └── api/
│       └── claude.ts          # API proxy endpoint
├── components/
│   ├── quick-cash/
│   │   └── QuickCashSystem.tsx  # Quick Cash System with real API
│   └── highticket/
│       └── HighTicketDashboard.tsx  # High-Ticket Dashboard with real API
├── .env.local                   # Environment configuration
└── API_SETUP_GUIDE.md          # This file
```

## How It Works

### API Proxy (`pages/api/claude.ts`)
- Acts as a secure proxy between your frontend and Anthropic API
- Protects your API key by keeping it server-side
- Handles error responses and logging
- Uses Claude Sonnet 4 model (`claude-sonnet-4-20250514`)

### Quick Cash System (`components/quick-cash/QuickCashSystem.tsx`)
- Uses the `/api/claude` proxy for all AI requests
- Features:
  - AI Service Arbitrage (Fiverr gigs)
  - Local Lead Generator
  - Upwork Gig Automation
  - Cold Outreach Machine
- Tracks API usage and costs
- Downloads generated assets as text files

### High-Ticket Dashboard (`components/highticket/HighTicketDashboard.tsx`)
- Uses the `/api/claude` proxy for AI features:
  - AI Consultant (sourcing, pricing, outreach, market analysis)
  - Pricing Engine (profit calculator)
  - Sales Script Generator
- Manages luxury product inventory
- Tracks sales pipeline and leads

## Running the Application

### Development Mode
```bash
npm run dev
```
Visit `http://localhost:3000` in your browser.

### Production Build
```bash
npm run build
npm start
```

## API Cost Monitoring

### Pricing (Claude Sonnet 4)
- Input: $3.00 per 1M tokens
- Output: $15.00 per 1M tokens

### Quick Cash System
- Displays real-time token usage per tool
- Shows cost per generation
- Tracks session totals

### High-Ticket Dashboard
- AI Consultant: ~1000 tokens per query
- Pricing Engine: ~500 tokens per analysis
- Sales Script: ~800 tokens per script

## Troubleshooting

### "ANTHROPIC_API_KEY not configured"
- Ensure `.env.local` exists in the project root
- Verify the API key is correct
- Restart the development server after adding the key

### "API request failed"
- Check your Anthropic API key is valid
- Verify you have credits in your Anthropic account
- Check the browser console for detailed error messages

### Module not found errors
- Run `npm install` to install dependencies
- Ensure `node_modules` exists

### TypeScript errors
- These are expected if TypeScript is not configured
- The code will work in JavaScript mode
- For full TypeScript support, ensure `tsconfig.json` is properly configured

## Security Notes

- **Never commit `.env.local` to version control**
- Add `.env.local` to your `.gitignore` file
- Use different API keys for development and production
- Rotate API keys if compromised

## Next Steps

1. Install dependencies: `npm install`
2. Configure your Anthropic API key in `.env.local`
3. Run the development server: `npm run dev`
4. Test the Quick Cash System
5. Test the High-Ticket Dashboard
6. Monitor API usage in the dashboards

## Support

For issues with:
- **Anthropic API**: Visit [console.anthropic.com](https://console.anthropic.com)
- **Next.js**: Visit [nextjs.org/docs](https://nextjs.org/docs)
- **This project**: Check the project README.md
