#!/usr/bin/env python3
"""
RUDIBOT Micro Revenue Checker
Quick revenue snapshot from Shopify - Phase 1 validation
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment
load_dotenv()

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def get_shopify_data():
    """Fetch revenue data from Shopify"""
    print(f"{Colors.BLUE}📊 Fetching Shopify Revenue Data{Colors.ENDC}")
    
    store_url = os.getenv('SHOPIFY_STORE_URL')
    token = os.getenv('SHOPIFY_ADMIN_TOKEN')
    api_version = os.getenv('SHOPIFY_API_VERSION', '2025-01')
    
    if not store_url or not token:
        print(f"{Colors.RED}❌ Shopify credentials not configured{Colors.ENDC}")
        return None
    
    try:
        # Get orders from last 30 days
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        url = f"https://{store_url}/admin/api/{api_version}/orders.json"
        headers = {
            'X-Shopify-Access-Token': token,
            'Content-Type': 'application/json'
        }
        
        params = {
            'status': 'any',
            'created_at_min': thirty_days_ago,
            'limit': 250
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        if response.status_code != 200:
            print(f"{Colors.RED}❌ Shopify API Error: {response.status_code}{Colors.ENDC}")
            print(f"   {response.text}")
            return None
        
        orders = response.json().get('orders', [])
        
        # Process revenue data
        revenue_data = {
            'total_orders': len(orders),
            'total_revenue': 0.0,
            'paid_orders': 0,
            'unpaid_orders': 0,
            'refunded_orders': 0,
            'daily_breakdown': {},
            'top_products': {},
            'currency': 'USD'
        }
        
        for order in orders:
            # Order details
            order_date = order.get('created_at', '')[:10]
            total_price = float(order.get('total_price', 0))
            financial_status = order.get('financial_status', 'pending')
            currency = order.get('currency', 'USD')
            
            # Set currency from first order
            if revenue_data['currency'] == 'USD' and currency != 'USD':
                revenue_data['currency'] = currency
            
            # Count by financial status
            if financial_status == 'paid':
                revenue_data['paid_orders'] += 1
                revenue_data['total_revenue'] += total_price
            elif financial_status == 'pending':
                revenue_data['unpaid_orders'] += 1
            elif financial_status == 'refunded':
                revenue_data['refunded_orders'] += 1
            
            # Daily breakdown
            if order_date not in revenue_data['daily_breakdown']:
                revenue_data['daily_breakdown'][order_date] = {
                    'orders': 0,
                    'revenue': 0.0
                }
            
            revenue_data['daily_breakdown'][order_date]['orders'] += 1
            if financial_status == 'paid':
                revenue_data['daily_breakdown'][order_date]['revenue'] += total_price
            
            # Product analysis
            for line_item in order.get('line_items', []):
                product_title = line_item.get('title', 'Unknown Product')
                quantity = int(line_item.get('quantity', 0))
                price = float(line_item.get('price', 0))
                
                if product_title not in revenue_data['top_products']:
                    revenue_data['top_products'][product_title] = {
                        'quantity': 0,
                        'revenue': 0.0
                    }
                
                revenue_data['top_products'][product_title]['quantity'] += quantity
                revenue_data['top_products'][product_title]['revenue'] += (price * quantity)
        
        return revenue_data
        
    except Exception as e:
        print(f"{Colors.RED}❌ Error fetching Shopify data: {str(e)}{Colors.ENDC}")
        return None

def display_revenue_report(data):
    """Display comprehensive revenue report"""
    if not data:
        return
    
    print(f"\n{Colors.BOLD}{Colors.CYAN}")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║              RUDIBOT REVENUE SNAPSHOT - LAST 30 DAYS         ║")
    print(f"╚══════════════════════════════════════════════════════════════╝{Colors.ENDC}")
    
    # Summary
    print(f"\n{Colors.BOLD}📈 SUMMARY{Colors.ENDC}")
    print(f"   💰 Total Revenue: {Colors.GREEN}${data['total_revenue']:.2f} {data['currency']}{Colors.ENDC}")
    print(f"   📦 Total Orders: {data['total_orders']}")
    print(f"   ✅ Paid Orders: {Colors.GREEN}{data['paid_orders']}{Colors.ENDC}")
    print(f"   ⏳ Pending Orders: {Colors.YELLOW}{data['unpaid_orders']}{Colors.ENDC}")
    print(f"   💸 Refunded Orders: {Colors.RED}{data['refunded_orders']}{Colors.ENDC}")
    
    # Average order value
    if data['paid_orders'] > 0:
        avg_order = data['total_revenue'] / data['paid_orders']
        print(f"   📊 Average Order Value: ${avg_order:.2f}")
    
    # Daily trend (last 7 days)
    print(f"\n{Colors.BOLD}📅 LAST 7 DAYS TREND{Colors.ENDC}")
    sorted_days = sorted(data['daily_breakdown'].items(), reverse=True)[:7]
    
    for date, day_data in sorted_days:
        revenue_color = Colors.GREEN if day_data['revenue'] > 0 else Colors.YELLOW
        print(f"   {date}: {day_data['orders']} orders, {revenue_color}${day_data['revenue']:.2f}{Colors.ENDC}")
    
    # Top products
    print(f"\n{Colors.BOLD}🏆 TOP PRODUCTS{Colors.ENDC}")
    sorted_products = sorted(data['top_products'].items(), key=lambda x: x[1]['revenue'], reverse=True)[:5]
    
    for i, (product, prod_data) in enumerate(sorted_products, 1):
        print(f"   {i}. {product}")
        print(f"      📊 {prod_data['quantity']} units, ${prod_data['revenue']:.2f} revenue")
    
    # Revenue indicators
    print(f"\n{Colors.BOLD}🎯 BUSINESS HEALTH{Colors.ENDC}")
    
    if data['total_revenue'] > 0:
        # Daily average
        daily_avg = data['total_revenue'] / 30
        print(f"   📊 Daily Average: ${daily_avg:.2f}")
        
        # Health indicators
        if daily_avg > 100:
            print(f"   {Colors.GREEN}🟢 Strong daily revenue${Colors.ENDC}")
        elif daily_avg > 50:
            print(f"   {Colors.YELLOW}🟡 Moderate daily revenue${Colors.ENDC}")
        else:
            print(f"   {Colors.RED}🔴 Low daily revenue${Colors.ENDC}")
        
        # Order completion rate
        completion_rate = (data['paid_orders'] / data['total_orders'] * 100) if data['total_orders'] > 0 else 0
        print(f"   📈 Order Completion Rate: {completion_rate:.1f}%")
        
        if completion_rate > 80:
            print(f"   {Colors.GREEN}✅ Excellent conversion rate{Colors.ENDC}")
        elif completion_rate > 60:
            print(f"   {Colors.YELLOW}⚠️  Good conversion rate{Colors.ENDC}")
        else:
            print(f"   {Colors.RED}❌ Low conversion rate - check payment issues{Colors.ENDC}")
    else:
        print(f"   {Colors.RED}❌ No revenue in last 30 days{Colors.ENDC}")
        print(f"   {Colors.YELLOW}💡 Check if orders exist or payment processing{Colors.ENDC}")

def main():
    """Main execution"""
    print(f"{Colors.BOLD}{Colors.BLUE}")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║              RUDIBOT MICRO REVENUE CHECKER                ║")
    print("║                    Phase 1 Tool                            ║")
    print(f"╚══════════════════════════════════════════════════════════════╝{Colors.ENDC}")
    
    print(f"\n{Colors.BOLD}📅 Analysis: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.ENDC}")
    print(f"📊 Period: Last 30 days")
    
    # Get data and display report
    revenue_data = get_shopify_data()
    display_revenue_report(revenue_data)
    
    # Next steps
    print(f"\n{Colors.BOLD}🚀 NEXT STEPS{Colors.ENDC}")
    
    if revenue_data and revenue_data['total_revenue'] > 0:
        print(f"   {Colors.GREEN}✅ Shopify connection working{Colors.ENDC}")
        print(f"   📈 Revenue data available for analysis")
        print(f"   🔄 Ready for Phase 2: Auto-Operation")
        print(f"   💡 Consider: Order automation, customer follow-up")
    else:
        print(f"   {Colors.YELLOW}⚠️  No revenue data detected{Colors.ENDC}")
        print(f"   🔧 Check: Shopify credentials, order history")
        print(f"   💡 Verify: Admin token permissions, store activity")
    
    print(f"\n{Colors.BOLD}═══════════════════════════════════════════════════════════════{Colors.ENDC}")
    
    return revenue_data is not None

if __name__ == "__main__":
    # Parse command line args
    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        success = main()
        sys.exit(0 if success else 1)
    else:
        print(f"{Colors.YELLOW}Usage: python micro_revenue.py --once{Colors.ENDC}")
        sys.exit(1)
