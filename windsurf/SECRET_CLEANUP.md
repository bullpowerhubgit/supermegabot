# Git History Secret Cleanup

## 1. Install BFG
```bash
brew install bfg
```

## 2. Replace secrets
```bash
# Replace specific secrets
bfg --replace-text secrets.txt
bfg --delete-files .env
```

## 3. Clean and push
```bash
git reflog expire --expire=now --all
git gc --prune=now --aggressive
git push origin main --force
```

## 4. Rotate all exposed keys
- Shopify API Key
- Telegram Bot Token
- OpenAI API Key
- Supabase Service Key
- Stripe Secret Key
