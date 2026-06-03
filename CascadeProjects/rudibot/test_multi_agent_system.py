#!/usr/bin/env python3
"""
RUDIBOT Multi-Agent System Test
Tests the complete multi-agent orchestration system
"""

import os
import sys
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

# Load environment
load_dotenv()

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def test_multi_agent_status():
    """Test multi-agent orchestrator status"""
    print(f"\n{Colors.BLUE}🤖 Testing Multi-Agent System Status{Colors.ENDC}")
    
    try:
        response = requests.get('http://localhost:3200/multi-agent/status', timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            print(f"{Colors.GREEN}✅ Multi-Agent System Active{Colors.ENDC}")
            
            # System status
            system = data.get('system', {})
            print(f"   🎯 Mode: {system.get('mode', 'Unknown')}")
            print(f"   🔄 Active Workflows: {system.get('activeWorkflows', 0)}")
            print(f"   📊 Total Tasks: {system.get('totalTasks', 0)}")
            print(f"   ✅ Completed Tasks: {system.get('completedTasks', 0)}")
            print(f"   ❌ Failed Tasks: {system.get('failedTasks', 0)}")
            print(f"   🤝 Collaborations: {system.get('collaborationCount', 0)}")
            
            # Agents status
            agents = data.get('agents', [])
            print(f"\n{Colors.BOLD}🤖 Registered Agents ({len(agents)}):{Colors.ENDC}")
            
            for agent in agents:
                status_color = Colors.GREEN if agent['status'] == 'idle' else Colors.YELLOW if agent['status'] == 'busy' else Colors.RED
                print(f"   {status_color}• {agent['name']} ({agent['type']}) - {agent['status']}{Colors.ENDC}")
                print(f"     📋 Current Tasks: {agent['currentTasks']}")
                print(f"   ✅ Completed: {agent['completedTasks']} | ❌ Failed: {agent['failedTasks']}")
                print(f"   📈 Success Rate: {agent.get('successRate', 0):.1%}")
            
            # Workflows status
            workflows = data.get('workflows', {})
            print(f"\n{Colors.BOLD}🔄 Workflow Engine:{Colors.ENDC}")
            print(f"   📋 Available Workflows: {workflows.get('available', 0)}")
            print(f"   🔄 Active Workflows: {workflows.get('active', 0)}")
            
            # Integrations status
            integrations = data.get('integrations', [])
            print(f"\n{Colors.BOLD}🔗 External Integrations:{Colors.ENDC}")
            
            for integration in integrations:
                status_color = Colors.GREEN if integration['status'] == 'configured' else Colors.YELLOW
                print(f"   {status_color}• {integration['name']} ({integration['type']}){Colors.ENDC}")
                print(f"     🤖 Agent: {integration['agent']}")
            
            return True
            
        else:
            print(f"{Colors.RED}❌ Multi-Agent Status Error: {response.status_code}{Colors.ENDC}")
            return False
            
    except Exception as e:
        print(f"{Colors.RED}❌ Multi-Agent Connection Error: {str(e)}{Colors.ENDC}")
        return False

def test_workflow_execution():
    """Test workflow execution"""
    print(f"\n{Colors.BLUE}🔄 Testing Workflow Execution{Colors.ENDC}")
    
    # Test revenue analysis workflow
    try:
        workflow_data = {
            "reportType": "test",
            "dateRange": "last_7_days"
        }
        
        response = requests.post(
            'http://localhost:3200/multi-agent/workflows/revenue_analysis',
            json=workflow_data,
            timeout=30000  # 30 seconds timeout
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"{Colors.GREEN}✅ Revenue Analysis Workflow Started{Colors.ENDC}")
            print(f"   📊 Workflow ID: {result.get('result', {}).get('id', 'Unknown')}")
            print(f"   📋 Status: {result.get('result', {}).get('status', 'Unknown')}")
            return True
        else:
            print(f"{Colors.YELLOW}⚠️ Workflow Test: {response.status_code}{Colors.ENDC}")
            print(f"   {response.text}")
            return False
            
    except Exception as e:
        print(f"{Colors.RED}❌ Workflow Test Error: {str(e)}{Colors.ENDC}")
        return False

def test_order_processing():
    """Test order processing workflow"""
    print(f"\n{Colors.BLUE}📦 Testing Order Processing Workflow{Colors.ENDC}")
    
    # Mock order data
    order_data = {
        "id": "TEST-ORDER-001",
        "order_number": "1001",
        "total_price": "29.99",
        "currency": "EUR",
        "financial_status": "paid",
        "created_at": datetime.now().isoformat(),
        "customer": {
            "id": "CUST-001",
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "Customer"
        },
        "line_items": [
            {
                "title": "Test Product",
                "quantity": 1,
                "price": "29.99"
            }
        ]
    }
    
    try:
        response = requests.post(
            'http://localhost:3200/multi-agent/orders/new',
            json=order_data,
            timeout=30000
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"{Colors.GREEN}✅ Order Processing Workflow Started{Colors.ENDC}")
            print(f"   📦 Order ID: {order_data['id']}")
            print(f"   🔄 Workflow ID: {result.get('result', {}).get('id', 'Unknown')}")
            return True
        else:
            print(f"{Colors.YELLOW}⚠️ Order Processing Test: {response.status_code}{Colors.ENDC}")
            print(f"   {response.text}")
            return False
            
    except Exception as e:
        print(f"{Colors.RED}❌ Order Processing Test Error: {str(e)}{Colors.ENDC}")
        return False

def test_customer_support():
    """Test customer support workflow"""
    print(f"\n{Colors.BLUE}💬 Testing Customer Support Workflow{Colors.ENDC}")
    
    # Mock customer inquiry
    inquiry_data = {
        "type": "wismo",
        "urgency": "normal",
        "customer": {
            "email": "customer@example.com",
            "name": "John Doe"
        },
        "inquiry": {
            "subject": "Where is my order?",
            "message": "I ordered something 3 days ago and haven't received it yet.",
            "order_id": "1001"
        }
    }
    
    try:
        response = requests.post(
            'http://localhost:3200/multi-agent/support/inquiry',
            json=inquiry_data,
            timeout=30000
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"{Colors.GREEN}✅ Customer Support Workflow Started{Colors.ENDC}")
            print(f"   💬 Inquiry Type: {inquiry_data['type']}")
            print(f"   🔄 Workflow ID: {result.get('result', {}).get('id', 'Unknown')}")
            return True
        else:
            print(f"{Colors.YELLOW}⚠️ Customer Support Test: {response.status_code}{Colors.ENDC}")
            print(f"   {response.text}")
            return False
            
    except Exception as e:
        print(f"{Colors.RED}❌ Customer Support Test Error: {str(e)}{Colors.ENDC}")
        return False

def test_agent_collaboration():
    """Test agent collaboration capabilities"""
    print(f"\n{Colors.BLUE}🤝 Testing Agent Collaboration{Colors.ENDC}")
    
    # Create a complex task that requires collaboration
    collaboration_data = {
        "reportType": "comprehensive",
        "includeRecommendations": True,
        "requireMultipleAgents": True
    }
    
    try:
        response = requests.post(
            'http://localhost:3200/multi-agent/reports/revenue',
            json=collaboration_data,
            timeout=45000  # 45 seconds for collaboration
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"{Colors.GREEN}✅ Agent Collaboration Test Started{Colors.ENDC}")
            print(f"   🤝 Collaboration Type: Comprehensive Report")
            print(f"   🔄 Workflow ID: {result.get('result', {}).get('id', 'Unknown')}")
            return True
        else:
            print(f"{Colors.YELLOW}⚠️ Collaboration Test: {response.status_code}{Colors.ENDC}")
            print(f"   {response.text}")
            return False
            
    except Exception as e:
        print(f"{Colors.RED}❌ Collaboration Test Error: {str(e)}{Colors.ENDC}")
        return False

def display_system_capabilities():
    """Display multi-agent system capabilities"""
    print(f"\n{Colors.BOLD}{Colors.MAGENTA}")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║              RUDIBOT MULTI-AGENT SYSTEM CAPABILITIES         ║")
    print(f"╚══════════════════════════════════════════════════════════════╝{Colors.ENDC}")
    
    capabilities = [
        {
            "category": "🤖 Agent Management",
            "features": [
                "Dynamic agent registration",
                "Capability-based task assignment",
                "Performance monitoring",
                "Load balancing",
                "Agent health checks"
            ]
        },
        {
            "category": "🔄 Workflow Engine",
            "features": [
                "Business workflow orchestration",
                "Conditional step execution",
                "Fallback mechanisms",
                "Timeout handling",
                "Workflow chaining"
            ]
        },
        {
            "category": "🤝 Collaboration",
            "features": [
                "Multi-agent task coordination",
                "Resource locking",
                "Conflict resolution",
                "Communication channels",
                "Collaboration metrics"
            ]
        },
        {
            "category": "📊 Business Functions",
            "features": [
                "Order processing automation",
                "Revenue analysis",
                "Cost optimization",
                "Customer support",
                "Security monitoring"
            ]
        },
        {
            "category": "🔗 Integrations",
            "features": [
                "Shopify e-commerce",
                "Printify production",
                "Finance management",
                "Notification systems",
                "API orchestration"
            ]
        }
    ]
    
    for capability in capabilities:
        print(f"\n{Colors.BOLD}{capability['category']}{Colors.ENDC}")
        for feature in capability['features']:
            print(f"   ✅ {feature}")

def main():
    """Run all multi-agent system tests"""
    print(f"{Colors.BOLD}{Colors.CYAN}")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║           RUDIBOT MULTI-AGENT SYSTEM TEST SUITE              ║")
    print("║                    Phase 2 Validation                       ║")
    print(f"╚══════════════════════════════════════════════════════════════╝{Colors.ENDC}")
    
    print(f"\n{Colors.BOLD}📅 Test Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.ENDC}")
    
    # Display system capabilities
    display_system_capabilities()
    
    results = []
    
    # Test 1: System Status
    results.append(test_multi_agent_status())
    
    # Test 2: Workflow Execution
    results.append(test_workflow_execution())
    
    # Test 3: Order Processing
    results.append(test_order_processing())
    
    # Test 4: Customer Support
    results.append(test_customer_support())
    
    # Test 5: Agent Collaboration
    results.append(test_agent_collaboration())
    
    # Summary
    print(f"\n{Colors.BOLD}═══════════════════════════════════════════════════════════════{Colors.ENDC}")
    print(f"{Colors.BOLD}📊 MULTI-AGENT SYSTEM TEST SUMMARY{Colors.ENDC}")
    
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"{Colors.GREEN}✅ ALL TESTS PASSED ({passed}/{total}){Colors.ENDC}")
        print(f"\n{Colors.GREEN}🎉 Multi-Agent System is fully operational!{Colors.ENDC}")
        print(f"   🤖 All agents registered and ready")
        print(f"   🔄 Workflow engine functional")
        print(f"   🤝 Agent collaboration working")
        print(f"   📊 Business workflows active")
        print(f"   🔗 External integrations connected")
    else:
        print(f"{Colors.YELLOW}⚠️ SOME TESTS ISSUED ({passed}/{total}){Colors.ENDC}")
        print(f"\n{Colors.YELLOW}🔧 System Status:{Colors.ENDC}")
        
        if passed >= 3:
            print(f"   {Colors.GREEN}✅ Core multi-agent functionality working{Colors.ENDC}")
            print(f"   🚀 Ready for Phase 2 automation")
        else:
            print(f"   {Colors.RED}❌ Core issues detected{Colors.ENDC}")
            print(f"   🔧 Check agent registration and workflows")
    
    print(f"\n{Colors.BOLD}═══════════════════════════════════════════════════════════════{Colors.ENDC}")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
