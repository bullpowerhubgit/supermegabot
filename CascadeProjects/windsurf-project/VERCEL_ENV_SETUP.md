# Vercel Environment Variables Setup Guide

## Team Configuration

- **Team Name:** bullpowerhubgit's projects
- **Team ID:** team_xulvdt7sib2RSt4BNoqVWeSy
- **Team URL:** [https://vercel.com/bullpowerhubgits-projects/](https://vercel.com/bullpowerhubgits-projects/)

---

## Critical Environment Variables (Immediate Setup)

### 1. AI Services (Required for QuickCash System)

```bash
ANTHROPIC_API_KEY=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
```

### 2. Application Environment

```bash
NODE_ENV=production
ENVIRONMENT=production
DEBUG=false
```

### 3. API Configuration

```bash
API_BASE_URL=https://api.anthropic.com/v1
API_VERSION=2023-06-01
API_TIMEOUT=30000
```

---

## Step-by-Step Setup

### 1. Access Vercel Dashboard

1. Go to: [https://vercel.com/bullpowerhubgits-projects/](https://vercel.com/bullpowerhubgits-projects/)
2. Login with your account
3. Select the QuickCash System project

### 2. Add Environment Variables

1. Go to **Settings** → **Environment Variables**
2. Add each variable from the list above
3. Set **Environment**: Production, Preview, Development
4. Click **Save**

### 3. Redeploy Application

1. Go to **Deployments**
2. Click **Redeploy** or push new commit
3. Wait for deployment to complete

---

## Optional Variables (Full Functionality)

### Backup AI Services

```bash
OPENAI_API_KEY=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
PERPLEXITY_API_KEY=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
```

### Database (if needed)

```bash
SUPABASE_URL=https://qyrjeckzacjaazkpvnjk.supabase.co
SUPABASE_ANON_KEY=sb_publishable_LY9XawaVKY67pIWISU27ww_hTNQszuP
SUPABASE_SERVICE_KEY=sb_secret__Bl843CKODUQ23rXUmheig_0Ehtb8uC
```

### Notifications (if needed)

```bash
TELEGRAM_BOT_TOKEN=8600739487:AAG_L4u82Y4UWPq-wGWzAdNC8bWJT99ASJI
TELEGRAM_CHAT_ID=8600739487
```

---

## Validation Checklist

After setting up Environment Variables:

- [ ] QuickCash System loads without API errors
- [ ] Anthropic API responds correctly
- [ ] All 4 Quick Cash tools are functional
- [ ] Cost tracking displays correctly
- [ ] Download feature works

---

## Troubleshooting

### Common Issues

1. **API Key Invalid**: Double-check ANTHROPIC_API_KEY format
2. **Build Fails**: Check for missing NODE_ENV=production
3. **Runtime Error**: Verify all required variables are set

### Debug Steps

1. Check Vercel Function Logs
2. Verify Environment Variables in dashboard
3. Test API key manually
4. Redeploy if variables changed

---

## Quick Access Links

- **Vercel Dashboard:** [https://vercel.com/bullpowerhubgits-projects/](https://vercel.com/bullpowerhubgits-projects/)
- **QuickCash System:** [Deploy URL after deployment]
- **Environment Variables:** Project Settings → Environment Variables

---

**Status:** Ready for deployment  
**Next Step:** Set Environment Variables → Deploy → Test
