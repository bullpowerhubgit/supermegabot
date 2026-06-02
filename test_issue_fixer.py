#!/usr/bin/env python3
"""
Test Script für Issue Fixer Agent
Testet den Workflow der automatischen Issue-Behebung
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agent_collaboration_framework import report_issue, get_dashboard_status
from issue_fixer_agent import start_issue_fixer, stop_issue_fixer, get_fixer_status

async def test_issue_fixer():
    """Test den Issue Fixer Workflow"""
    print("🧪 Starte Issue Fixer Test...")
    
    # 1. Erstelle Test-Issues
    print("\n📋 Erstelle Test-Issues...")
    
    test_issues = [
        {
            "title": "Service Port 8080 Down",
            "description": "Web service on port 8080 is not responding",
            "severity": "high",
            "reporter": "test_script",
            "tags": ["service_failure", "port_8080"]
        },
        {
            "title": "Memory Usage High",
            "description": "System memory usage is above 90%",
            "severity": "medium",
            "reporter": "test_script",
            "tags": ["memory", "health"]
        },
        {
            "title": "API Endpoint Timeout",
            "description": "API endpoint /api/products is timing out",
            "severity": "critical",
            "reporter": "test_script",
            "tags": ["api", "timeout"]
        }
    ]
    
    issue_ids = []
    for issue_data in test_issues:
        issue_id = await report_issue(
            issue_data["title"],
            issue_data["description"],
            issue_data["severity"],
            issue_data["reporter"],
            issue_data["tags"]
        )
        issue_ids.append(issue_id)
        print(f"  ✅ Issue erstellt: {issue_id} - {issue_data['title']}")
    
    # 2. Starte Issue Fixer Agent
    print("\n🤖 Starte Issue Fixer Agent...")
    await start_issue_fixer()
    
    # 3. Warte kurz damit der Agent Issues verarbeiten kann
    print("\n⏳ Warte 10 Sekunden für Issue-Verarbeitung...")
    await asyncio.sleep(10)
    
    # 4. Prüfe Status
    print("\n📊 Prüfe Issue Fixer Status...")
    status = await get_fixer_status()
    
    print(f"\n  Agent Name: {status['name']}")
    print(f"  Running: {status['running']}")
    print(f"  Open Issues: {status['open_issues']}")
    print(f"  Total Attempts: {status['statistics']['total_attempts']}")
    print(f"  Success Rate: {status['statistics']['success_rate']:.1%}")
    
    # 5. Prüfe Dashboard Status
    print("\n📈 Prüfe Dashboard Status...")
    dashboard = get_dashboard_status()
    
    print(f"\n  Total Agents: {len(dashboard['agents'])}")
    print(f"  Open Issues: {dashboard['issues']['open']}")
    print(f"  Critical Issues: {dashboard['issues']['critical']}")
    
    # 6. Stoppe Agent
    print("\n🛑 Stoppe Issue Fixer Agent...")
    await stop_issue_fixer()
    
    print("\n✅ Test abgeschlossen!")
    print("\n📝 Zusammenfassung:")
    print(f"  - {len(issue_ids)} Test-Issues erstellt")
    print(f"  - Issue Fixer Agent gestartet und gestoppt")
    print(f"  - Status: {status['running']}")
    print(f"  - Open Issues: {status['open_issues']}")

if __name__ == "__main__":
    try:
        asyncio.run(test_issue_fixer())
    except KeyboardInterrupt:
        print("\n⚠️ Test abgebrochen")
    except Exception as e:
        print(f"\n❌ Test fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()
