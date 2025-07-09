#!/usr/bin/env python3
import requests
import json
import time
from datetime import datetime
import sys

# Base URL from frontend/.env
BASE_URL = "https://47af4de8-f4e6-4dea-9315-8292e5904188.preview.emergentagent.com/api"

# Sample webhook payload for testing
SAMPLE_WEBHOOK_PAYLOAD = {
    "ticker": "BTC",
    "action": "buy",
    "price": 45000,
    "quantity": 0.1,
    "timestamp": "2025-07-09T16:00:00Z"
}

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
            print(f"Uptime: {status_data['uptime']}")
            print(f"Total Webhooks: {status_data['total_webhooks']}")
            print(f"Successful Forwards: {status_data['successful_forwards']}")
            print(f"Failed Forwards: {status_data['failed_forwards']}")
            print(f"Hyperliquid Connected: {status_data['hyperliquid_connected']}")
            if status_data.get('balance') is not None:
                print(f"Balance: ${status_data['balance']}")
            return True
        else:
            print(f"❌ Status endpoint test failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing status endpoint: {str(e)}")
        return False

def test_logs_endpoint():
    """Test the logs endpoint"""
    print("\n=== Testing Logs Endpoint ===")
    
    url = f"{BASE_URL}/logs"
    
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            logs_data = response.json()
            log_count = len(logs_data.get('logs', []))
            print("✅ Logs endpoint test passed")
            print(f"Retrieved {log_count} logs")
            
            # Display a few recent logs if available
            if log_count > 0:
                print("\nRecent logs:")
                for log in logs_data['logs'][:3]:
                    print(f"- [{log.get('level', 'INFO')}] {log.get('message', 'No message')}")
            return True
        else:
            print(f"❌ Logs endpoint test failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing logs endpoint: {str(e)}")
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
            
            switch_response = requests.post(switch_url, json=target_env)
            if switch_response.status_code == 200:
                print(f"✅ Successfully switched to {target_env}")
                
                # Verify the switch
                verify_response = requests.get(get_url)
                if verify_response.status_code == 200:
                    new_env = verify_response.json().get('environment')
                    if new_env == target_env:
                        print(f"✅ Environment verified as {new_env}")
                        
                        # Switch back to original environment
                        switch_back = requests.post(switch_url, json=current_env)
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
    """Test the webhooks endpoint"""
    print("\n=== Testing Webhooks Endpoint ===")
    
    url = f"{BASE_URL}/webhooks"
    
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            webhooks_data = response.json()
            webhook_count = len(webhooks_data.get('webhooks', []))
            print("✅ Webhooks endpoint test passed")
            print(f"Retrieved {webhook_count} webhooks")
            
            # Display a few recent webhooks if available
            if webhook_count > 0:
                print("\nRecent webhooks:")
                for webhook in webhooks_data['webhooks'][:2]:
                    print(f"- ID: {webhook.get('id')}")
                    print(f"  Timestamp: {webhook.get('timestamp')}")
                    print(f"  Status: {webhook.get('status')}")
            return True
        else:
            print(f"❌ Webhooks endpoint test failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing webhooks endpoint: {str(e)}")
        return False

def test_responses_endpoint():
    """Test the Hyperliquid responses endpoint"""
    print("\n=== Testing Responses Endpoint ===")
    
    url = f"{BASE_URL}/responses"
    
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            responses_data = response.json()
            response_count = len(responses_data.get('responses', []))
            print("✅ Responses endpoint test passed")
            print(f"Retrieved {response_count} Hyperliquid responses")
            
            # Display a few recent responses if available
            if response_count > 0:
                print("\nRecent responses:")
                for resp in responses_data['responses'][:2]:
                    print(f"- ID: {resp.get('id')}")
                    print(f"  Webhook ID: {resp.get('webhook_id')}")
                    print(f"  Status: {resp.get('status')}")
            return True
        else:
            print(f"❌ Responses endpoint test failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing responses endpoint: {str(e)}")
        return False

def run_all_tests():
    """Run all tests and report results"""
    print("=" * 80)
    print("TRADINGVIEW TO HYPERLIQUID MIDDLEWARE BACKEND TESTS")
    print("=" * 80)
    print(f"Testing against: {BASE_URL}")
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Track test results
    results = {}
    
    # Test webhook endpoint
    webhook_success, webhook_id = test_webhook_endpoint()
    results["Webhook Endpoint"] = webhook_success
    
    # Test status endpoint
    status_success = test_status_endpoint()
    results["Status Endpoint"] = status_success
    
    # Test logs endpoint
    logs_success = test_logs_endpoint()
    results["Logs Endpoint"] = logs_success
    
    # Test environment switching
    env_success = test_environment_switching()
    results["Environment Switching"] = env_success
    
    # Test webhooks endpoint
    webhooks_success = test_webhooks_endpoint()
    results["Webhooks Endpoint"] = webhooks_success
    
    # Test responses endpoint
    responses_success = test_responses_endpoint()
    results["Responses Endpoint"] = responses_success
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False
    
    print("\nOVERALL RESULT:", "✅ ALL TESTS PASSED" if all_passed else "❌ SOME TESTS FAILED")
    print("=" * 80)
    
    return all_passed

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)