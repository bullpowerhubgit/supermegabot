# SuperMegaBot Production Setup Guide

## ✅ Completed Infrastructure

- **ecosystem.config.js** - PM2 production configuration created
- **health.js** - Health check script created
- **package.json** - Updated with PM2 scripts and dependencies
- **.env** - Added Shopify Store2 configuration

## 🔐 Security Actions Required (Manual)

### 1. Rotate Exposed GitHub Token
**Current:** `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`
**Action:**
1. Go to https://github.com/settings/tokens
2. Revoke the old token
3. Create new token with required scopes
4. Update `.env` line: `GITHUB_TOKEN=ghp_NEW_TOKEN_HERE`

### 2. Rotate Shopify Store1 Token
**Current:** `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`
**Action:**
1. Go to Shopify Admin → Apps → suiteapi-2
2. Revoke old token
3. Generate new access token
4. Update `.env` line: `SHOPIFY_ACCESS_TOKEN=shpat_NEW_TOKEN_HERE`

### 3. Configure Shopify Store2
**Current:** `shpat_REPLACE_WITH_NEW_TOKEN`
**Action:**
1. Go to Soolar Shopify Admin → Settings → Apps → Develop apps
2. Create new custom app with scopes:
   - read_products, write_products
   - read_orders, write_orders
   - read_customers, write_customers
   - read_inventory, write_inventory
3. Generate access token
4. Update `.env` line: `SHOPIFY_STORE2_TOKEN=shpat_NEW_TOKEN_HERE`

### 4. Update Supabase Service Key
**Current:** `YOUR_SUPABASE_KEY_HERE_REPLACE_WITH_REAL_KEY`
**Action:**
1. Go to https://supabase.com/dashboard/project/qyrjeckzacjaazkpvnjk/settings/api
2. Copy service_role key
3. Update `.env` line: `SUPABASE_SERVICE_KEY=eyJ...REAL_KEY`

### 5. Configure Google Ads (Optional)
**Action:**
1. Go to Google Ads API Console
2. Generate developer token and OAuth credentials
3. Update `.env` lines:
   - `GOOGLE_ADS_DEVELOPER_TOKEN=`
   - `GOOGLE_ADS_CLIENT_ID=`
   - `GOOGLE_ADS_CLIENT_SECRET=`
   - `GOOGLE_ADS_REFRESH_TOKEN=`
   - `GOOGLE_ADS_CUSTOMER_ID=`

## 🚀 Deployment Steps

### 1. Install Dependencies
```bash
npm install
```

### 2. Create Logs Directory
```bash
mkdir -p logs
```

### 3. Syntax Check
```bash
npm run check
```

### 4. Health Check
```bash
npm run health
```

### 5. Start with PM2
```bash
npm run pm2:start
```

### 6. Check Status
```bash
npm run pm2:status
```

### 7. Save PM2 Configuration
```bash
npm run pm2:save
```

### 8. Enable Auto-Start on Mac Reboot
```bash
pm2 save
pm2 startup
```
**Then copy and run the exact command shown**, e.g.:
```bash
sudo env PATH=$PATH:/opt/homebrew/bin pm2 startup launchd -u rudolfsarkany --hp /Users/rudolfsarkany
```

### 9. Final Save
```bash
pm2 save
```

## 📊 Monitoring

### View Logs
```bash
npm run pm2:logs
```

### Restart All Services
```bash
npm run pm2:restart
```

### Stop All Services
```bash
npm run stop
```

### Health Check
```bash
npm run health
```

## 🔍 Troubleshooting

### PM2 Commands
```bash
pm2 list              # List all processes
pm2 logs [app-name]   # View specific app logs
pm2 monit             # Monitor CPU/Memory
pm2 flush             # Clear all logs
```

### Common Issues

**Bot not starting:**
```bash
rm -f .bot*.lock
pm2 restart autopilot-bot-public
pm2 restart autopilot-bot-control
```

**Port conflicts:**
```bash
lsof -i :8888  # Check dashboard port
lsof -i :8000  # Check bot port
```

**Environment issues:**
```bash
node -e "require('dotenv').config(); console.log('Telegram:', !!process.env.TELEGRAM_BOT_TOKEN)"
```

## ✅ Checklist

- [ ] GitHub token rotated
- [ ] Shopify Store1 token rotated
- [ ] Shopify Store2 token configured
- [ ] Supabase service key updated
- [ ] Dependencies installed (`npm install`)
- [ ] Logs directory created (`mkdir -p logs`)
- [ ] Syntax check passed (`npm run check`)
- [ ] Health check passed (`npm run health`)
- [ ] PM2 started (`npm run pm2:start`)
- [ ] PM2 auto-start configured (`pm2 save && pm2 startup`)
- [ ] All services running (`npm run pm2:status`)

## 🎯 Production URLs

- **Dashboard:** http://localhost:8888
- **Telegram Bot:** Integrated via TELEGRAM_BOT_TOKEN
- **Health Check:** Run `npm run health`

## 📝 Notes

- All sensitive data is in `.env` (already in .gitignore)
- PM2 logs are stored in `logs/` directory
- Auto-restart is enabled for all services
- Memory limits are configured to prevent crashes
- Lock files are automatically cleaned on restart
