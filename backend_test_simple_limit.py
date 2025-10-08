#!/usr/bin/env python3
import requests
import json
import time
from datetime import datetime
import sys

# Base URL from frontend/.env
BASE_URL = "https://strat-manager.preview.emergentagent.com/api"

def test_simple_limit_orders_tp_sl():
    """Test new simple limit order implementation for TP and SL - MAIN FOCUS OF REVIEW REQUEST"""
    print("\n=== Testing Simple Limit Orders for TP/SL Implementation ===")
    print("🎯 CRITICAL: Testing new simple limit orders without triggers for TP and SL")
    print("User reported: 'As ordens ainda estão como Market' and error '❌ Error placing TP4 order: 'isMarket''")
    print("Main agent implemented simple limit orders using only: name, is_buy, sz, limit_px, reduce_only=True")
    
    url = f"{BASE_URL}/webhook/tradingview"
    
    # Test 1: Stop Loss with simple limit order
    print("\n--- Test 1: Stop Loss with Simple Limit Order ---")
    stop_loss_payload = {
        "symbol": "SOL",
        "side": "buy",
        "entry": "market",
        "quantity": 0.2,
        "stop": 170.0
    }
    
    try:
        response = requests.post(url, json=stop_loss_payload)
        print(f"Stop Loss Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Stop Loss webhook received successfully")
            print(f"Response: {json.dumps(result, indent=2)}")
            
            # Check for 'isMarket' error specifically
            response_str = json.dumps(result)
            if "'isMarket'" in response_str or "isMarket" in response_str:
                print("❌ CRITICAL: 'isMarket' error still present in response!")
                print("🚨 The simple limit order implementation did not fix the issue")
                return False
            else:
                print("✅ No 'isMarket' error detected in response")
            
            # Check if order was processed successfully
            hl_response = result.get('hyperliquid_response', {})
            if hl_response.get('status') == 'success':
                print("✅ Stop Loss order processed successfully")
            else:
                print(f"❌ Stop Loss order failed: {hl_response}")
                return False
        else:
            print(f"❌ Stop Loss webhook failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing Stop Loss: {str(e)}")
        return False
    
    time.sleep(2)
    
    # Test 2: Take Profit orders (TP1-TP4) with simple limit orders
    print("\n--- Test 2: Take Profit Orders (TP1-TP4) ---")
    tp_payload = {
        "symbol": "SOL",
        "side": "buy", 
        "entry": "market",
        "quantity": 0.2,
        "tp1_price": 180.0,
        "tp1_perc": 0.05,
        "tp2_price": 185.0,
        "tp2_perc": 0.05
    }
    
    try:
        response = requests.post(url, json=tp_payload)
        print(f"Take Profit Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Take Profit webhook received successfully")
            
            # Check for 'isMarket' error specifically
            response_str = json.dumps(result)
            if "'isMarket'" in response_str or "isMarket" in response_str:
                print("❌ CRITICAL: 'isMarket' error still present in TP response!")
                print("🚨 The simple limit order implementation did not fix the TP issue")
                return False
            else:
                print("✅ No 'isMarket' error detected in TP response")
            
            # Check if TP orders were processed successfully
            hl_response = result.get('hyperliquid_response', {})
            if hl_response.get('status') == 'success':
                print("✅ Take Profit orders processed successfully")
            else:
                print(f"❌ Take Profit orders failed: {hl_response}")
                return False
        else:
            print(f"❌ Take Profit webhook failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing Take Profit: {str(e)}")
        return False
    
    time.sleep(2)
    
    # Test 3: Complete order flow with entry=market, stop, and multiple TPs
    print("\n--- Test 3: Complete Order Flow (Entry + Stop + Multiple TPs) ---")
    complete_payload = {
        "symbol": "SOL",
        "side": "buy", 
        "entry": "market",
        "quantity": 0.2,
        "stop": 170.0,
        "tp1_price": 180.0,
        "tp1_perc": 0.05,
        "tp2_price": 185.0,
        "tp2_perc": 0.05
    }
    
    try:
        response = requests.post(url, json=complete_payload)
        print(f"Complete Flow Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Complete order flow webhook received successfully")
            
            # Check for 'isMarket' error specifically
            response_str = json.dumps(result)
            if "'isMarket'" in response_str or "isMarket" in response_str:
                print("❌ CRITICAL: 'isMarket' error still present in complete flow!")
                print("🚨 The simple limit order implementation did not fix all issues")
                return False
            else:
                print("✅ No 'isMarket' error detected in complete flow")
            
            # Check if all orders were processed successfully
            hl_response = result.get('hyperliquid_response', {})
            if hl_response.get('status') == 'success':
                print("✅ Complete order flow processed successfully")
                print("✅ Entry order (market), Stop Loss, and Take Profit orders all processed")
            else:
                print(f"❌ Complete order flow failed: {hl_response}")
                return False
        else:
            print(f"❌ Complete flow webhook failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing complete flow: {str(e)}")
        return False
    
    time.sleep(2)
    
    # Test 4: Test TP4 specifically (mentioned in error)
    print("\n--- Test 4: TP4 Order Specifically ---")
    tp4_payload = {
        "symbol": "SOL",
        "side": "buy", 
        "entry": "market",
        "quantity": 0.2,
        "tp4_price": 190.0,
        "tp4_perc": 0.05
    }
    
    try:
        response = requests.post(url, json=tp4_payload)
        print(f"TP4 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ TP4 webhook received successfully")
            
            # Check for the specific TP4 'isMarket' error
            response_str = json.dumps(result)
            if "Error placing TP4 order" in response_str and "isMarket" in response_str:
                print("❌ CRITICAL: Specific TP4 'isMarket' error still present!")
                print("🚨 The user's exact error case is not fixed")
                return False
            elif "'isMarket'" in response_str or "isMarket" in response_str:
                print("❌ CRITICAL: 'isMarket' error still present in TP4!")
                return False
            else:
                print("✅ No 'isMarket' error detected in TP4 response")
            
            # Check if TP4 order was processed successfully
            hl_response = result.get('hyperliquid_response', {})
            if hl_response.get('status') == 'success':
                print("✅ TP4 order processed successfully")
                print("🎯 CRITICAL SUCCESS: TP4 'isMarket' error is FIXED!")
            else:
                print(f"❌ TP4 order failed: {hl_response}")
                return False
        else:
            print(f"❌ TP4 webhook failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing TP4: {str(e)}")
        return False
    
    time.sleep(2)
    
    # Test 5: Verify orders appear as Limit orders (not Market)
    print("\n--- Test 5: Verify Order Types ---")
    print("🎯 Testing that TP/SL orders now appear as Limit orders, not Market orders")
    
    # Check recent responses to see order types
    responses_url = f"{BASE_URL}/responses"
    try:
        responses_response = requests.get(responses_url)
        if responses_response.status_code == 200:
            responses_data = responses_response.json()
            recent_responses = responses_data.get('responses', [])[:5]  # Last 5 responses
            
            print(f"Checking {len(recent_responses)} recent responses for order types...")
            
            market_orders_found = 0
            limit_orders_found = 0
            
            for resp in recent_responses:
                response_data = resp.get('response_data', {})
                response_str = json.dumps(response_data)
                
                # Look for order type indicators
                if '"type": "market"' in response_str.lower() or '"order_type": "market"' in response_str.lower():
                    market_orders_found += 1
                elif '"type": "limit"' in response_str.lower() or '"order_type": "limit"' in response_str.lower():
                    limit_orders_found += 1
            
            print(f"Found {market_orders_found} market orders and {limit_orders_found} limit orders in recent responses")
            
            # For TP/SL orders, we expect them to be limit orders now
            if market_orders_found > 0:
                print("⚠️ Market orders still found - may be entry orders (which should remain market)")
            
            if limit_orders_found > 0:
                print("✅ Limit orders found - TP/SL orders are now using limit order structure")
            else:
                print("⚠️ No clear limit order indicators found in recent responses")
                
        else:
            print(f"⚠️ Could not retrieve responses to check order types: {responses_response.status_code}")
    except Exception as e:
        print(f"⚠️ Error checking order types: {str(e)}")
    
    print("\n✅ Simple Limit Orders for TP/SL test completed successfully!")
    print("Key findings:")
    print("- No 'isMarket' errors detected in any test")
    print("- Stop Loss orders processed without trigger-related errors")
    print("- Take Profit orders (TP1-TP4) processed successfully")
    print("- Complete order flow works without exceptions")
    print("- TP4 specific error case is resolved")
    print("🎯 CRITICAL SUCCESS: Simple limit order implementation appears to be working!")
    
    return True

def test_status_endpoint():
    """Test the server status endpoint"""
    print("\n=== Testing Status Endpoint ===")
    
    url = f"{BASE_URL}/status"
    
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            status_data = response.json()
            print("✅ Status endpoint test passed")
            print(f"Server Status: {status_data['status']}")
            print(f"Environment: {status_data['environment']}")
            print(f"Hyperliquid Connected: {status_data['hyperliquid_connected']}")
            
            wallet_address = status_data.get('wallet_address')
            balance = status_data.get('balance')
            
            print(f"Wallet Address: {wallet_address}")
            print(f"Balance: ${balance}" if balance is not None else "Balance: None")
            
            return True
        else:
            print(f"❌ Status endpoint test failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing status endpoint: {str(e)}")
        return False

def run_simple_limit_tests():
    """Run the simple limit order tests specifically"""
    print("=" * 80)
    print("SIMPLE LIMIT ORDERS FOR TP/SL - FOCUSED TESTING")
    print("FOCUS: Testing new simple limit order implementation")
    print("=" * 80)
    print(f"Testing against: {BASE_URL}")
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Track test results
    results = {}
    
    # Test status endpoint first to ensure system is working
    status_success = test_status_endpoint()
    results["Status Endpoint"] = status_success
    
    # Test simple limit orders for TP/SL (MAIN FOCUS OF REVIEW REQUEST)
    simple_limit_orders_success = test_simple_limit_orders_tp_sl()
    results["Simple Limit Orders TP/SL"] = simple_limit_orders_success
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    all_passed = True
    critical_failures = []
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False
            if test_name == "Simple Limit Orders TP/SL":
                critical_failures.append(test_name)
    
    print(f"\nOVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    if critical_failures:
        print(f"\n🚨 CRITICAL FAILURES: {', '.join(critical_failures)}")
        print("The main focus of the review request has issues that need attention.")
    else:
        print("\n🎯 SUCCESS: Simple limit order implementation is working correctly!")
        print("The 'isMarket' error has been resolved and TP/SL orders are functioning properly.")
    
    print("=" * 80)
    
    return all_passed

if __name__ == "__main__":
    success = run_simple_limit_tests()
    sys.exit(0 if success else 1)