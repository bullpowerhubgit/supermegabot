#!/usr/bin/env python3
"""
RUDIBOT Live Connection Test
Tests all critical API connections before going live
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
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def test_shopify_connection():
    """Test Shopify API connection"""
    print(f"\n{Colors.BLUE}🛍️  Testing Shopify Connection{Colors.ENDC}")
    
    store_url = os.getenv('SHOPIFY_STORE_URL')
    token = os.getenv('SHOPIFY_ADMIN_TOKEN')
    api_version = os.getenv('SHOPIFY_API_VERSION', '2025-01')
    
    if not store_url or not token:
        print(f"{Colors.RED}❌ Shopify credentials not found in .env{Colors.ENDC}")
        return False
    
    if 'your-store' in store_url or 'your_real' in token:
        print(f"{Colors.YELLOW}⚠️  Shopify credentials are placeholders{Colors.ENDC}")
        return False
    
    try:
        # Test store info
        url = f"https://{store_url}/admin/api/{api_version}/shop.json"
        headers = {
            'X-Shopify-Access-Token': token,
            'Content-Type': 'application/json'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            shop_data = response.json().get('shop', {})
            print(f"{Colors.GREEN}✅ Shopify Store: {shop_data.get('name', 'Unknown')}{Colors.ENDC}")
            print(f"   📍 Domain: {shop_data.get('domain', 'Unknown')}")
            print(f"   💰 Currency: {shop_data.get('currency', 'Unknown')}")
            return True
        else:
            print(f"{Colors.RED}❌ Shopify API Error: {response.status_code}{Colors.ENDC}")
            print(f"   {response.text}")
            return False
            
    except Exception as e:
        print(f"{Colors.RED}❌ Shopify Connection Error: {str(e)}{Colors.ENDC}")
        return False

def test_server_health():
    """Test local server health"""
    print(f"\n{Colors.BLUE}🏥 Testing Server Health{Colors.ENDC}")
    
    try:
        response = requests.get('http://localhost:3200/api/health', timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"{Colors.GREEN}✅ Server Status: {data.get('status', 'Unknown')}{Colors.ENDC}")
            print(f"   ⏱️  Uptime: {data.get('uptime', 'Unknown')}")
            print(f"   💾 Memory: {data.get('memory', 'Unknown')}")
            print(f"   🔧 Node: {data.get('node', 'Unknown')}")
            
            # Check environment
            env = data.get('env', {})
            shopify_ok = env.get('shopify1', False)
            print(f"   🛍️  Shopify Configured: {'✅' if shopify_ok else '❌'}")
            
            return True
        else:
            print(f"{Colors.RED}❌ Server Health Check Failed: {response.status_code}{Colors.ENDC}")
            return False
            
    except Exception as e:
        print(f"{Colors.RED}❌ Server Connection Error: {str(e)}{Colors.ENDC}")
        print(f"   {Colors.YELLOW}💡 Make sure server is running: npm start{Colors.ENDC}")
        return False

def test_shopify_orders():
    """Test Shopify orders endpoint"""
    print(f"\n{Colors.BLUE}📦 Testing Shopify Orders{Colors.ENDC}")
    
    store_url = os.getenv('SHOPIFY_STORE_URL')
    token = os.getenv('SHOPIFY_ADMIN_TOKEN')
    api_version = os.getenv('SHOPIFY_API_VERSION', '2025-01')
    
    if not store_url or not token:
        print(f"{Colors.RED}❌ Shopify credentials not found{Colors.ENDC}")
        return False
    
    try:
        url = f"https://{store_url}/admin/api/{api_version}/orders.json?limit=5"
        headers = {
            'X-Shopify-Access-Token': token,
            'Content-Type': 'application/json'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            orders = response.json().get('orders', [])
            print(f"{Colors.GREEN}✅ Orders Retrieved: {len(orders)} recent orders{Colors.ENDC}")
            
            if orders:
                latest = orders[0]
                print(f"   📋 Latest Order: #{latest.get('order_number', 'Unknown')}")
                print(f"   💰 Total: {latest.get('total_price', 'Unknown')} {latest.get('currency', '')}")
                print(f"   📅 Date: {latest.get('created_at', 'Unknown')[:10]}")
            
            return True
        else:
            print(f"{Colors.RED}❌ Orders API Error: {response.status_code}{Colors.ENDC}")
            return False
            
    except Exception as e:
        print(f"{Colors.RED}❌ Orders Error: {str(e)}{Colors.ENDC}")
        return False

def main():
    """Run all connection tests"""
    print(f"{Colors.BOLD}{Colors.BLUE}")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║           RUDIBOT LIVE CONNECTION TEST SUITE                ║")
    print("║                    Phase 1 Validation                       ║")
    print(f"╚══════════════════════════════════════════════════════════════╝{Colors.ENDC}")
    
    print(f"\n{Colors.BOLD}📅 Test Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.ENDC}")
    
    results = []
    
    # Test server first
    results.append(test_server_health())
    
    # Test Shopify connections
    results.append(test_shopify_connection())
    results.append(test_shopify_orders())
    
    # Summary
    print(f"\n{Colors.BOLD}═══════════════════════════════════════════════════════════════{Colors.ENDC}")
    print(f"{Colors.BOLD}📊 TEST SUMMARY{Colors.ENDC}")
    
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"{Colors.GREEN}✅ ALL TESTS PASSED ({passed}/{total}){Colors.ENDC}")
        print(f"\n{Colors.GREEN}🎉 RUDIBOT is ready for Phase 1!{Colors.ENDC}")
        print(f"   🚀 Shopify connection is live")
        print(f"   📊 Orders and products can be fetched")
        print(f"   🔄 Ready for auto-operation setup")
    else:
        print(f"{Colors.RED}❌ SOME TESTS FAILED ({passed}/{total}){Colors.ENDC}")
        print(f"\n{Colors.YELLOW}🔧 Next steps:{Colors.ENDC}")
        
        if not results[0]:  # Server failed
            print(f"   1. Start server: npm start")
            print(f"   2. Check port 3200 is available")
        
        if not results[1]:  # Shopify connection failed
            print(f"   1. Update .env with real Shopify credentials")
            print(f"   2. Create admin token with correct scopes")
            print(f"   3. Verify store URL is correct")
        
        if not results[2]:  # Orders failed
            print(f"   1. Check admin token permissions")
            print(f"   2. Verify API version compatibility")
    
    print(f"\n{Colors.BOLD}═══════════════════════════════════════════════════════════════{Colors.ENDC}")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
