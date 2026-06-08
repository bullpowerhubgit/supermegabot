# Windsurf Agent Rules for SuperMegaBot

## Architecture
- Core bot: /Users/rudolfsarkany/supermegabot/
- Dashboard: port 8888
- Telegram bot: port 3200
- Army Commander: rudibot-army/army_commander.py

## Rules
1. Never hardcode credentials - always use os.getenv()
2. All agents must report status via rudibot-army/shared/bus.py
3. Dashboard endpoints follow /api/<resource> convention
4. Python files: use type hints, handle exceptions explicitly
5. Run deep_scan_repair.py before committing

## Integration Points
- army_commander.py: register new agents here
- core/mega_orchestrator.py: main dispatch
- dashboard/server.py: add new API endpoints here
