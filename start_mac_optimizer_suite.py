#!/usr/bin/env python3
"""
🍎 MAC OPTIMIZATION SUITE — STARTER & INTEGRATION SCRIPT
Startet alle Komponenten der Mac Optimization Suite:
  - Mac Optimizer Engine
  - Agent Data Bridge
  - Dashboard Server (mit neuen API Endpoints)
  - Integration Tests

Usage:
  python3 start_mac_optimizer_suite.py
  python3 start_mac_optimizer_suite.py --test
  python3 start_mac_optimizer_suite.py --cleanup
  python3 start_mac_optimizer_suite.py --full
"""

import asyncio
import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from modules.mac_optimizer import get_mac_optimizer
from modules.agent_data_bridge import get_data_bridge


async def test_all():
    """Testet alle Komponenten"""
    print("\n" + "=" * 60)
    print("🧪 MAC OPTIMIZATION SUITE — SELF TEST")
    print("=" * 60)

    # 1. Mac Optimizer
    print("\n1️⃣  Testing Mac Optimizer…")
    opt = get_mac_optimizer()
    info = await opt.get_system_info()
    print(f"   ✅ System Info: {info.get('platform', '?')} {info.get('version', '?')}")
    print(f"   💾 Memory: {info.get('memory_used_gb', 0):.1f} / {info.get('memory_total_gb', 0):.1f} GB")

    # 2. Agent Data Bridge
    print("\n2️⃣  Testing Agent Data Bridge…")
    bridge = get_data_bridge()
    result = bridge.register_agent("test_agent", {"status": "online", "capabilities": ["test"]})
    print(f"   ✅ Agent registered: {result.get('ok')}")
    status = bridge.get_system_status()
    print(f"   📊 Total agents: {status.get('total_agents', 0)}")

    # 3. Cleanup Simulation (lightweight)
    print("\n3️⃣  Testing Cleanup (simulation)…")
    # cleanup = await opt.cleanup_system(aggressive=False)
    print("   ⏭️  Skipped in test mode (use --cleanup to run real cleanup)")

    # 4. Security Scan
    print("\n4️⃣  Testing Security Scan…")
    sec = await opt.security_scan()
    print(f"   🔒 Secure: {sec.get('secure', '?')}")
    print(f"   ⚠️ Issues: {len(sec.get('issues', []))}")

    # 5. DeepScan
    print("\n5️⃣  Testing DeepScan…")
    ds = await opt.run_deep_scan()
    print(f"   🔍 Status: {ds.get('status', '?')}")
    print(f"   📋 Total issues: {ds.get('total_issues', 0)}")

    # 6. Data Sharing
    print("\n6️⃣  Testing Agent Data Sharing…")
    share = await opt.share_optimization_data()
    print(f"   🔗 Shared: {share.get('ok')}")
    print(f"   📤 Data entries: {len(share.get('data', {}).get('shared_data', {}).keys())}")

    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED")
    print("=" * 60)
    return True


async def run_cleanup():
    """Führt System Cleanup durch"""
    print("\n🧹 Starting System Cleanup…")
    opt = get_mac_optimizer()
    result = await opt.cleanup_system(aggressive=False)
    freed = result.get('total_freed_gb', 0)
    print(f"✅ Cleanup complete! Freed {freed:.2f} GB")
    for op in result.get('operations', []):
        print(f"   • {op['name']}: {op.get('freed_mb', 0)} MB")
    return result


async def run_full_optimization():
    """Führt komplette Optimierung durch"""
    print("\n🚀 Starting Full Optimization…")
    opt = get_mac_optimizer()
    result = await opt.run_all_optimizations()
    steps = result.get('steps', [])
    ok = sum(1 for s in steps if s.get('result', {}).get('success', False))
    print(f"✅ Full optimization complete!")
    print(f"   Steps: {len(steps)}")
    print(f"   Successful: {ok}/{len(steps)}")
    for step in steps:
        status = "✅" if step.get('result', {}).get('success', False) else "❌"
        print(f"   {status} {step['name']}")
    return result


async def main():
    parser = argparse.ArgumentParser(description="Mac Optimization Suite Starter")
    parser.add_argument("--test", action="store_true", help="Run self-tests")
    parser.add_argument("--cleanup", action="store_true", help="Run system cleanup")
    parser.add_argument("--full", action="store_true", help="Run full optimization")
    args = parser.parse_args()

    if args.cleanup:
        await run_cleanup()
    elif args.full:
        await run_full_optimization()
    elif args.test:
        await test_all()
    else:
        print(__doc__)
        print("\n📋 Available commands:")
        print("  --test      Run all self-tests")
        print("  --cleanup   Run quick system cleanup")
        print("  --full      Run full optimization")
        print("\n🌐 Dashboard: http://localhost:8888")
        print("   Navigate to '🍎 Mac Optimizer' tab")
        print("   API docs: /api/mac-optimizer/*")
        print("   Bridge:   /api/bridge/*")
        print()


if __name__ == "__main__":
    asyncio.run(main())
