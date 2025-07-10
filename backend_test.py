#!/usr/bin/env python3
import requests
import json
import time
from datetime import datetime
import sys

# Base URL from frontend/.env
BASE_URL = "https://2862ac8e-57ac-4911-8d7a-896ae91802bf.preview.emergentagent.com/api"

# Sample webhook payload for testing - Updated to match backend expectations
SAMPLE_WEBHOOK_PAYLOAD = {
    "symbol": "BTC",  # Backend expects "symbol", not "ticker"
    "action": "buy",
    "price": 45000,
    "quantity": 0.001,  # Smaller quantity for testing
    "timestamp": "2025-07-09T16:00:00Z"
}

# Additional test payloads for comprehensive testing
SAMPLE_SELL_PAYLOAD = {
    "symbol": "ETH",
    "action": "sell", 
    "price": 3200,
    "quantity": 0.01,
    "timestamp": "2025-07-09T16:00:00Z"
}

def test_real_order_execution():
    """Test real order execution on Hyperliquid testnet - KEY FOCUS AREA"""
    print("\n=== Testing Real Order Execution ===")
    print("🎯 CRITICAL: Testing real order placement on Hyperliquid testnet")
    print("This is the main focus of the review request")
    
    # Test BUY order
    print("\n--- Testing BUY Order ---")
    buy_payload = {
        "symbol": "BTC",
        "action": "buy",
        "price": 45000,
        "quantity": 0.001,
        "timestamp": datetime.now().isoformat()
    }
    
    url = f"{BASE_URL}/webhook/tradingview"
    
    try:
        response = requests.post(url, json=buy_payload)
        print(f"BUY Order Status Code: {response.status_code}")
        
        if response.status_code == 200:
            buy_result = response.json()
            print("✅ BUY webhook received successfully")
            
            # Check if order was actually executed
            hl_response = buy_result.get('hyperliquid_response', {})
            hl_status = hl_response.get('status')
            
            if hl_status == 'success':
                print("✅ BUY order executed successfully on Hyperliquid!")
                order_details = hl_response.get('order_details', {})
                hl_result = order_details.get('hyperliquid_response', {})
                
                # Look for order ID in response
                if 'status' in hl_result and hl_result['status'] == 'ok':
                    print(f"✅ Hyperliquid confirmed order execution: {hl_result}")
                    if 'response' in hl_result and 'data' in hl_result['response']:
                        order_data = hl_result['response']['data']
                        if 'statuses' in order_data:
                            for status in order_data['statuses']:
                                if 'resting' in status:
                                    order_id = status['resting'].get('oid')
                                    if order_id:
                                        print(f"🎯 REAL ORDER ID: {order_id}")
                else:
                    print(f"⚠️ Order may have failed: {hl_result}")
            else:
                print(f"❌ BUY order execution failed: {hl_response.get('message', 'Unknown error')}")
                print(f"Error details: {hl_response.get('error', 'No error details')}")
                return False
                
        else:
            print(f"❌ BUY webhook failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing BUY order: {str(e)}")
        return False
    
    # Wait a moment before next order
    time.sleep(2)
    
    # Test SELL order
    print("\n--- Testing SELL Order ---")
    sell_payload = {
        "symbol": "ETH", 
        "action": "sell",
        "price": 3200,
        "quantity": 0.01,
        "timestamp": datetime.now().isoformat()
    }
    
    try:
        response = requests.post(url, json=sell_payload)
        print(f"SELL Order Status Code: {response.status_code}")
        
        if response.status_code == 200:
            sell_result = response.json()
            print("✅ SELL webhook received successfully")
            
            # Check if order was actually executed
            hl_response = sell_result.get('hyperliquid_response', {})
            hl_status = hl_response.get('status')
            
            if hl_status == 'success':
                print("✅ SELL order executed successfully on Hyperliquid!")
                order_details = hl_response.get('order_details', {})
                hl_result = order_details.get('hyperliquid_response', {})
                
                # Look for order ID in response
                if 'status' in hl_result and hl_result['status'] == 'ok':
                    print(f"✅ Hyperliquid confirmed order execution: {hl_result}")
                    if 'response' in hl_result and 'data' in hl_result['response']:
                        order_data = hl_result['response']['data']
                        if 'statuses' in order_data:
                            for status in order_data['statuses']:
                                if 'resting' in status:
                                    order_id = status['resting'].get('oid')
                                    if order_id:
                                        print(f"🎯 REAL ORDER ID: {order_id}")
                else:
                    print(f"⚠️ Order may have failed: {hl_result}")
            else:
                print(f"❌ SELL order execution failed: {hl_response.get('message', 'Unknown error')}")
                print(f"Error details: {hl_response.get('error', 'No error details')}")
                return False
                
        else:
            print(f"❌ SELL webhook failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing SELL order: {str(e)}")
        return False
    
    print("\n✅ Real order execution test completed successfully!")
    print("Both BUY and SELL orders were processed and sent to Hyperliquid testnet")
    return True

def test_webhook_endpoint():
    """Test the TradingView webhook endpoint"""
    print("\n=== Testing Webhook Endpoint ===")
    
    url = f"{BASE_URL}/webhook/tradingview"
    
    try:
        response = requests.post(url, json=SAMPLE_WEBHOOK_PAYLOAD)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Webhook endpoint test passed")
            print(f"Response: {json.dumps(response.json(), indent=2)}")
            return True, response.json().get('webhook_id')
        else:
            print(f"❌ Webhook endpoint test failed: {response.text}")
            return False, None
    except Exception as e:
        print(f"❌ Error testing webhook endpoint: {str(e)}")
        return False, None

def test_webhook_endpoint():
    """Test the TradingView webhook endpoint"""
    print("\n=== Testing Webhook Endpoint ===")
    
    url = f"{BASE_URL}/webhook/tradingview"
    
    try:
        response = requests.post(url, json=SAMPLE_WEBHOOK_PAYLOAD)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Webhook endpoint test passed")
            print(f"Response: {json.dumps(response.json(), indent=2)}")
            return True, response.json().get('webhook_id')
        else:
            print(f"❌ Webhook endpoint test failed: {response.text}")
            return False, None
    except Exception as e:
        print(f"❌ Error testing webhook endpoint: {str(e)}")
        return False, None

def test_status_endpoint():
    """Test the server status endpoint - Focus on wallet address and balance"""
    print("\n=== Testing Status Endpoint ===")
    print("🎯 Focus: Wallet address and balance retrieval from Hyperliquid testnet")
    
    url = f"{BASE_URL}/status"
    
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            status_data = response.json()
            print("✅ Status endpoint test passed")
            print(f"Server Status: {status_data['status']}")
            print(f"Environment: {status_data['environment']}")
            print(f"Uptime: {status_data['uptime']}")
            print(f"Total Webhooks: {status_data['total_webhooks']}")
            print(f"Successful Forwards: {status_data['successful_forwards']}")
            print(f"Failed Forwards: {status_data['failed_forwards']}")
            print(f"Hyperliquid Connected: {status_data['hyperliquid_connected']}")
            
            # Key focus areas from review request
            wallet_address = status_data.get('wallet_address')
            balance = status_data.get('balance')
            
            print(f"\n🔍 KEY TESTING POINTS:")
            print(f"Wallet Address: {wallet_address}")
            print(f"Balance: ${balance}" if balance is not None else "Balance: None")
            
            # Validate key requirements
            success = True
            if not wallet_address:
                print("❌ CRITICAL: Wallet address is missing from status response")
                success = False
            else:
                print("✅ Wallet address is present in status response")
                
            if balance is None:
                print("❌ CRITICAL: Balance is None - not fetching real data from Hyperliquid testnet")
                success = False
            else:
                print(f"✅ Balance retrieved: ${balance} - appears to be real data from Hyperliquid testnet")
                
            if status_data['environment'] != 'testnet':
                print(f"❌ CRITICAL: Environment should be 'testnet', got '{status_data['environment']}'")
                success = False
            else:
                print("✅ Environment correctly set to testnet")
                
            if not status_data['hyperliquid_connected']:
                print("❌ CRITICAL: Hyperliquid connection failed")
                success = False
            else:
                print("✅ Hyperliquid connection successful")
                
            return success
        else:
            print(f"❌ Status endpoint test failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing status endpoint: {str(e)}")
        return False

def test_logs_endpoint():
    """Test the logs endpoint - Check if serialization issues are fixed"""
    print("\n=== Testing Logs Endpoint ===")
    print("🎯 Focus: Testing if MongoDB ObjectId serialization issues are fixed")
    
    url = f"{BASE_URL}/logs"
    
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            logs_data = response.json()
            log_count = len(logs_data.get('logs', []))
            print("✅ Logs endpoint test passed - Serialization issues appear to be FIXED!")
            print(f"Retrieved {log_count} logs")
            
            # Display a few recent logs if available
            if log_count > 0:
                print("\nRecent logs:")
                for log in logs_data['logs'][:3]:
                    print(f"- [{log.get('level', 'INFO')}] {log.get('message', 'No message')}")
                    if log.get('timestamp'):
                        print(f"  Timestamp: {log.get('timestamp')}")
            return True
        else:
            print(f"❌ Logs endpoint test failed: {response.text}")
            print("❌ CRITICAL: Serialization issues NOT fixed - still returning error")
            return False
    except Exception as e:
        print(f"❌ Error testing logs endpoint: {str(e)}")
        print("❌ CRITICAL: Serialization issues NOT fixed - exception occurred")
        return False

def test_hyperliquid_connection():
    """Test Hyperliquid connection specifically with the provided testnet private key"""
    print("\n=== Testing Hyperliquid Connection ===")
    print("🎯 Focus: Verify connection to Hyperliquid testnet with provided private key")
    print("Private Key: 0x978fafbb4b1bf1e197c3dff8dad11b2253fbf8fdbba01c4f5977d5ccaaa3ee54")
    
    # Test through status endpoint which includes connection test
    url = f"{BASE_URL}/status"
    
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            status_data = response.json()
            
            # Check Hyperliquid connection status
            hl_connected = status_data.get('hyperliquid_connected', False)
            environment = status_data.get('environment')
            balance = status_data.get('balance')
            wallet_address = status_data.get('wallet_address')
            
            print(f"Environment: {environment}")
            print(f"Hyperliquid Connected: {hl_connected}")
            print(f"Wallet Address: {wallet_address}")
            print(f"Balance: ${balance}" if balance is not None else "Balance: None")
            
            success = True
            
            if not hl_connected:
                print("❌ CRITICAL: Hyperliquid connection failed")
                success = False
            else:
                print("✅ Hyperliquid connection successful")
                
            if environment != 'testnet':
                print(f"❌ CRITICAL: Should be connected to testnet, got {environment}")
                success = False
            else:
                print("✅ Connected to testnet environment")
                
            if not wallet_address:
                print("❌ CRITICAL: Wallet address not derived from private key")
                success = False
            else:
                print(f"✅ Wallet address derived: {wallet_address}")
                
            if balance is None:
                print("❌ CRITICAL: Balance not retrieved from Hyperliquid testnet")
                success = False
            else:
                print(f"✅ Real balance retrieved from Hyperliquid testnet: ${balance}")
                
            return success
        else:
            print(f"❌ Failed to test Hyperliquid connection: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing Hyperliquid connection: {str(e)}")
        return False

def test_environment_switching():
    """Test environment switching between testnet and mainnet"""
    print("\n=== Testing Environment Switching ===")
    
    # First, get current environment
    get_url = f"{BASE_URL}/environment"
    
    try:
        response = requests.get(get_url)
        if response.status_code == 200:
            current_env = response.json().get('environment')
            print(f"Current environment: {current_env}")
            
            # Switch to the other environment
            target_env = "mainnet" if current_env == "testnet" else "testnet"
            switch_url = f"{BASE_URL}/environment"
            
            # The API expects a query parameter, not a JSON body
            switch_response = requests.post(f"{switch_url}?environment={target_env}")
            if switch_response.status_code == 200:
                print(f"✅ Successfully switched to {target_env}")
                
                # Verify the switch
                verify_response = requests.get(get_url)
                if verify_response.status_code == 200:
                    new_env = verify_response.json().get('environment')
                    if new_env == target_env:
                        print(f"✅ Environment verified as {new_env}")
                        
                        # Switch back to original environment
                        switch_back = requests.post(f"{switch_url}?environment={current_env}")
                        if switch_back.status_code == 200:
                            print(f"✅ Successfully switched back to {current_env}")
                            return True
                        else:
                            print(f"❌ Failed to switch back to original environment: {switch_back.text}")
                    else:
                        print(f"❌ Environment verification failed. Expected {target_env}, got {new_env}")
                else:
                    print(f"❌ Failed to verify environment switch: {verify_response.text}")
            else:
                print(f"❌ Failed to switch environment: {switch_response.text}")
        else:
            print(f"❌ Failed to get current environment: {response.text}")
        
        return False
    except Exception as e:
        print(f"❌ Error testing environment switching: {str(e)}")
        return False

def test_webhooks_endpoint():
    """Test the webhooks endpoint - Check if serialization issues are fixed"""
    print("\n=== Testing Webhooks Endpoint ===")
    print("🎯 Focus: Testing if MongoDB ObjectId serialization issues are fixed")
    
    url = f"{BASE_URL}/webhooks"
    
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            webhooks_data = response.json()
            webhook_count = len(webhooks_data.get('webhooks', []))
            print("✅ Webhooks endpoint test passed - Serialization issues appear to be FIXED!")
            print(f"Retrieved {webhook_count} webhooks")
            
            # Display a few recent webhooks if available
            if webhook_count > 0:
                print("\nRecent webhooks:")
                for webhook in webhooks_data['webhooks'][:2]:
                    print(f"- ID: {webhook.get('id')}")
                    print(f"  Timestamp: {webhook.get('timestamp')}")
                    print(f"  Status: {webhook.get('status')}")
                    print(f"  Source: {webhook.get('source')}")
            return True
        else:
            print(f"❌ Webhooks endpoint test failed: {response.text}")
            print("❌ CRITICAL: Serialization issues NOT fixed - still returning error")
            return False
    except Exception as e:
        print(f"❌ Error testing webhooks endpoint: {str(e)}")
        print("❌ CRITICAL: Serialization issues NOT fixed - exception occurred")
        return False

def test_responses_endpoint():
    """Test the Hyperliquid responses endpoint - Check if serialization issues are fixed"""
    print("\n=== Testing Responses Endpoint ===")
    print("🎯 Focus: Testing if MongoDB ObjectId serialization issues are fixed")
    
    url = f"{BASE_URL}/responses"
    
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            responses_data = response.json()
            response_count = len(responses_data.get('responses', []))
            print("✅ Responses endpoint test passed - Serialization issues appear to be FIXED!")
            print(f"Retrieved {response_count} Hyperliquid responses")
            
            # Display a few recent responses if available
            if response_count > 0:
                print("\nRecent responses:")
                for resp in responses_data['responses'][:2]:
                    print(f"- ID: {resp.get('id')}")
                    print(f"  Webhook ID: {resp.get('webhook_id')}")
                    print(f"  Status: {resp.get('status')}")
                    print(f"  Timestamp: {resp.get('timestamp')}")
            return True
        else:
            print(f"❌ Responses endpoint test failed: {response.text}")
            print("❌ CRITICAL: Serialization issues NOT fixed - still returning error")
            return False
    except Exception as e:
        print(f"❌ Error testing responses endpoint: {str(e)}")
        print("❌ CRITICAL: Serialization issues NOT fixed - exception occurred")
        return False

def run_all_tests():
    """Run all tests and report results"""
    print("=" * 80)
    print("TRADINGVIEW TO HYPERLIQUID MIDDLEWARE BACKEND TESTS")
    print("FOCUS: Updated backend with fixed serialization and real Hyperliquid connection")
    print("=" * 80)
    print(f"Testing against: {BASE_URL}")
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Track test results
    results = {}
    
    # Test Hyperliquid connection first (key focus area)
    hl_connection_success = test_hyperliquid_connection()
    results["Hyperliquid Connection"] = hl_connection_success
    
    # Test status endpoint (key focus area)
    status_success = test_status_endpoint()
    results["Status Endpoint"] = status_success
    
    # Test webhook endpoint to generate some data
    webhook_success, webhook_id = test_webhook_endpoint()
    results["Webhook Endpoint"] = webhook_success
    
    # Test previously failing endpoints (key focus area)
    logs_success = test_logs_endpoint()
    results["Logs Endpoint"] = logs_success
    
    webhooks_success = test_webhooks_endpoint()
    results["Webhooks Endpoint"] = webhooks_success
    
    responses_success = test_responses_endpoint()
    results["Responses Endpoint"] = responses_success
    
    # Test environment switching
    env_success = test_environment_switching()
    results["Environment Switching"] = env_success
    
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
            # Mark critical failures
            if test_name in ["Hyperliquid Connection", "Status Endpoint", "Logs Endpoint", "Webhooks Endpoint", "Responses Endpoint"]:
                critical_failures.append(test_name)
    
    print(f"\nOVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    if critical_failures:
        print(f"\n🚨 CRITICAL FAILURES: {', '.join(critical_failures)}")
        print("These are the key areas mentioned in the review request that need attention.")
    
    print("=" * 80)
    
    return all_passed

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)