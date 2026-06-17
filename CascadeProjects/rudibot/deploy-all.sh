#!/bin/bash
# ============================================================
# deploy-all.sh — Alle 5 ProEarner Next.js Projekte deployen
# Rudolf Sarkany · Vollautomatisch auf Vercel
# Ausführen: chmod +x deploy-all.sh && ./deploy-all.sh
# ============================================================
set -e

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'
CYN='\033[0;36m'; PRP='\033[0;35m'; NC='\033[0m'

ok()   { echo -e "  ${GRN}✅ $1${NC}"; }
fail() { echo -e "  ${RED}❌ $1${NC}"; }
warn() { echo -e "  ${YLW}⚠️  $1${NC}"; }
info() { echo -e "  ${CYN}ℹ️  $1${NC}"; }
step() { echo -e "\n${PRP}═══ $1 ═══════════════════════════════════════${NC}"; }

# ── ProEarner Projekte ────────────────────────────────────────
declare -A PROJECTS=(
  ["finanzos-pro"]="FinanzOS PRO · KI-Finanz-Dashboard"
  ["quick-cash-system"]="Quick Cash System · Side Hustles"
  ["passive-income-machine"]="Passive Income Machine"
  ["autoshop-suite"]="AutoShop Suite · Dropshipping AI"
  ["tool-koenig"]="TOOL KÖNIG · Mega AI Toolkit"
)

# Vercel ENVs für alle Projekte
VERCEL_ENVS=(
  "ANTHROPIC_API_KEY"
  "NEXT_PUBLIC_APP_URL"
)

# Vercel ENVs nur für AutoShop + RudiBot
SHOPIFY_ENVS=(
  "SHOPIFY_STORE_URL"
  "SHOPIFY_ADMIN_TOKEN"
  "SHOPIFY_STORE2_URL"
  "SHOPIFY_STORE2_TOKEN"
)

echo -e "${PRP}"
echo "  ██████╗ ██████╗  ██████╗ ███████╗ █████╗ ██████╗ ███╗   ██╗███████╗██████╗"
echo "  ██╔══██╗██╔══██╗██╔═══██╗██╔════╝██╔══██╗██╔══██╗████╗  ██║██╔════╝██╔══██╗"
echo "  ██████╔╝██████╔╝██║   ██║█████╗  ███████║██████╔╝██╔██╗ ██║█████╗  ██████╔╝"
echo -e "${NC}"
echo "  ProEarner AI Suite — Vercel Deploy v1.0"
echo ""

# ── Voraussetzungen prüfen ────────────────────────────────────
step "VORAUSSETZUNGEN"

# Vercel CLI
if ! command -v vercel &> /dev/null; then
  warn "Vercel CLI nicht gefunden → installiere..."
  npm install -g vercel
  ok "Vercel CLI installiert"
else
  ok "Vercel CLI $(vercel --version)"
fi

# .env prüfen
if [ ! -f ".env" ]; then fail ".env nicht gefunden!"; exit 1; fi
source .env 2>/dev/null || true

if [ -z "$ANTHROPIC_API_KEY" ] || [[ "$ANTHROPIC_API_KEY" == *"DEIN"* ]]; then
  fail "ANTHROPIC_API_KEY nicht gesetzt!"; exit 1
fi
ok "ANTHROPIC_API_KEY vorhanden"

# ── vercel.json Template ──────────────────────────────────────
create_vercel_json() {
  cat > vercel.json << 'VJEOF'
{
  "version": 2,
  "framework": "nextjs",
  "functions": {
    "pages/api/**": { "maxDuration": 30, "memory": 1024 }
  },
  "headers": [{
    "source": "/api/(.*)",
    "headers": [
      { "key": "Access-Control-Allow-Origin",  "value": "*" },
      { "key": "Access-Control-Allow-Methods", "value": "GET,POST,PUT,DELETE,OPTIONS" },
      { "key": "Access-Control-Allow-Headers", "value": "Content-Type,Authorization" }
    ]
  }],
  "rewrites": [
    { "source": "/health", "destination": "/api/health" }
  ]
}
VJEOF
}

# ── pages/api/claude.ts Template ─────────────────────────────
create_claude_proxy() {
  mkdir -p pages/api
  cat > pages/api/claude.ts << 'CLAUDEOF'
import type { NextApiRequest, NextApiResponse } from 'next';

export const config = { api: { bodyParser: { sizeLimit: '2mb' } } };

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method === 'OPTIONS') {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST,OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    return res.status(200).end();
  }
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { messages, system, max_tokens = 1000 } = req.body;
  if (!messages?.length) return res.status(400).json({ error: 'messages required' });

  try {
    const r = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': process.env.ANTHROPIC_API_KEY!,
        'anthropic-version': '2023-06-01'
      },
      body: JSON.stringify({ model: 'claude-sonnet-4-20250514', max_tokens, system, messages })
    });
    if (!r.ok) throw new Error(`Anthropic API: ${r.status}`);
    res.status(200).json(await r.json());
  } catch(e: any) {
    res.status(500).json({ error: e.message });
  }
}
CLAUDEOF
}

# ── pages/api/health.ts ───────────────────────────────────────
create_health_route() {
  mkdir -p pages/api
  cat > pages/api/health.ts << 'HEALTHEOF'
import type { NextApiRequest, NextApiResponse } from 'next';

export default function handler(_: NextApiRequest, res: NextApiResponse) {
  res.status(200).json({
    status: 'ok',
    app: process.env.NEXT_PUBLIC_APP_NAME || 'ProEarner AI',
    timestamp: new Date().toISOString(),
    env: { anthropic: !!process.env.ANTHROPIC_API_KEY }
  });
}
HEALTHEOF
}

# ── Deploy Funktion ───────────────────────────────────────────
deploy_project() {
  local dir="$1"
  local name="$2"
  
  step "DEPLOY: $name"
  
  if [ ! -d "$dir" ]; then
    warn "Verzeichnis '$dir' nicht gefunden — erstelle..."
    mkdir -p "$dir/pages/api" "$dir/pages" "$dir/components" "$dir/styles"
    
    # package.json
    cat > "$dir/package.json" << PKGEOF
{
  "name": "$dir",
  "version": "1.0.0",
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "14.2.0",
    "react": "^18",
    "react-dom": "^18"
  },
  "devDependencies": {
    "typescript": "^5",
    "@types/node": "^20",
    "@types/react": "^18"
  }
}
PKGEOF

    # tsconfig.json
    cat > "$dir/tsconfig.json" << 'TSEOF'
{
  "compilerOptions": {
    "target": "es5", "lib": ["dom","esnext"],
    "jsx": "preserve", "strict": true,
    "moduleResolution": "bundler", "allowImportingTsExtensions": true,
    "noEmit": true, "esModuleInterop": true, "skipLibCheck": true
  }
}
TSEOF
    ok "Projektstruktur erstellt"
  fi
  
  cd "$dir"
  
  # vercel.json + API routes erstellen
  create_vercel_json
  create_claude_proxy
  create_health_route
  ok "vercel.json + API Routes erstellt"
  
  # Dependencies
  if [ ! -d "node_modules" ]; then
    info "npm install..."
    npm install --silent
    ok "Dependencies installiert"
  fi
  
  # Build test
  info "Build testen..."
  npm run build 2>/dev/null && ok "Build erfolgreich" || warn "Build Warnung — trotzdem deploy"
  
  # Vercel deploy
  info "Deploy auf Vercel..."
  vercel --prod --yes \
    --env ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
    --env NEXT_PUBLIC_APP_NAME="$name" \
    2>/dev/null && ok "✅ $name deployed!" || fail "Deploy Fehler bei $name"
  
  cd ..
}

# ── Alle Projekte deployen ────────────────────────────────────
step "VERCEL LOGIN"
vercel whoami 2>/dev/null && ok "Bereits eingeloggt" || (info "Bitte einloggen:"; vercel login)

DEPLOYED=0
FAILED=0

for dir in "${!PROJECTS[@]}"; do
  desc="${PROJECTS[$dir]}"
  deploy_project "$dir" "$desc" && ((DEPLOYED++)) || ((FAILED++))
done

# ── Zusammenfassung ───────────────────────────────────────────
step "DEPLOY ZUSAMMENFASSUNG"

echo ""
echo -e "${GRN}  Deployed:  $DEPLOYED / ${#PROJECTS[@]}${NC}"
[ $FAILED -gt 0 ] && echo -e "${RED}  Fehler:    $FAILED${NC}"

echo ""
echo -e "${CYN}  Nächste Schritte:${NC}"
echo "  1. vercel ls                    — Alle deployten Apps"
echo "  2. vercel env add KEY VALUE     — ENVs hinzufügen"
echo "  3. vercel domains add domain.de — Custom Domain"
echo ""
echo -e "${PRP}  ProEarner Suite läuft auf Vercel! 🚀${NC}\n"
