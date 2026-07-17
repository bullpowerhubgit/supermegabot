# Autonomous Loop — SuperMegaBot

```
Claude Code / Agents  →  Tests (CI)  →  Deploy (Railway/Vercel)
        ↑                                         ↓
   Analytics plan  ←  PostHog/Plausible  ←  Stripe + Lemon + Email
```

## Run

```bash
# Full cycle (agents + payments + analytics + backlog)
python3 -m modules.autonomous_loop

# Quick (skip heavy Claude teams)
python3 -m modules.autonomous_loop --quick --no-notify
```

## HTTP

```http
POST /api/autonomous-loop/run
{"quick": false}

GET /api/autonomous-loop/status
```

## Agent teams

```bash
# via dashboard
POST /api/agents/run
{"team": "autonomous_loop", "task": "Raise MRR"}

{"team": "claude_collab", "task": "Weekly growth"}
```

## Scheduler

- `claude_collab` — every 2h  
- `autonomous_loop` — every 3h  

## CI/CD

| Layer | Mechanism |
|-------|-----------|
| GitHub Actions `deploy.yml` | syntax + guards on every push to `main` |
| GitHub Actions `autonomous_loop.yml` | every 6h + on loop file changes |
| GitHub Actions `claude_agent.yml` | daily Claude maintenance |
| Railway | auto-deploy on `main` (GitHub App) |
| Vercel | auto-deploy per connected project |

## Integrations

| System | Env | Role |
|--------|-----|------|
| Stripe (bullpower only) | `STRIPE_SECRET_KEY` | subs, invoices, balance |
| Lemon Squeezy | `LEMON_SQUEEZY_API_KEY`, `LEMON_SQUEEZY_STORE_ID` | shop catalog autopilot |
| Resend | `RESEND_API_KEY` | onboarding emails D0/D1/D3/D7 |
| Loops | `LOOPS_API_KEY` | contact sync (optional) |
| Plausible | `PLAUSIBLE_API_KEY`, `PLAUSIBLE_SITE_ID` | traffic metrics |
| PostHog | `POSTHOG_API_KEY`, `POSTHOG_PROJECT_ID` | product analytics |
| Claude / AI chain | `ANTHROPIC_*` + fallbacks | plan next iteration |

## Outputs

- `data/autonomous_loop/latest.json` — full report  
- `data/autonomous_loop/next_iteration.json` — machine plan  
- `data/autonomous_loop/BACKLOG.md` — human backlog for Claude Code  

## Rule

Never install secrets without `python3 scripts/api_precheck.py`.
