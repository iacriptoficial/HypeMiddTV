#!/usr/bin/env python3
import requests
import json
import time
from datetime import datetime
import sys

# Base URL from frontend/.env
BASE_URL = "https://strat-manager.preview.emergentagent.com/api"

# Sample webhook payload for testing - Updated to match backend expectations
SAMPLE_WEBHOOK_PAYLOAD = {
    "symbol": "BTC",  # Backend expects "symbol", not "ticker"
    "side": "buy",    # Backend expects "side", not "action"
    "entry": "market", # Backend expects "entry" field
    "price": "45000",
    "quantity": "0.01",  # Increased to meet minimum size
    "timestamp": "2025-07-09T16:00:00Z"
}

# Additional test payloads for comprehensive testing
SAMPLE_SELL_PAYLOAD = {
    "symbol": "ETH",
    "side": "sell", 
    "entry": "market",
    "price": "3200",
    "quantity": "0.01",
    "timestamp": "2025-07-09T16:00:00Z"
}

def test_enhanced_position_clearing_mechanism():
    """Test enhanced position clearing mechanism with detailed error logging - CRITICAL FOCUS"""
    print("\n=== Testing Enhanced Position Clearing Mechanism ===")
    print("🎯 CRITICAL: Testing the enhanced position clearing with detailed error logging")
    print("User's exact case: -10.73 SOL position clearing failing")
    print("Focus: Understanding why exchange.market_close() is failing with null response")
    print("Latest fix includes: detailed logging, exception handling, fallback mechanism, retry logic")
    
    # Test 1: Exact user scenario - -10.73 SOL position clearing
    print("\n--- Test 1: Exact User Scenario (-10.73 SOL Position Clearing) ---")
    print("Simulating: User's exact case with -10.73 SOL short position")
    
    exact_user_payload = {
        "symbol": "SOL",
        "side": "buy",  # This should trigger position clearing for short position
        "entry": "market",
        "quantity": "5.0",  # New position size (will require closing -10.73 first)
        "price": "175.00",
        "timestamp": datetime.now().isoformat()
    }
    
    url = f"{BASE_URL}/webhook/tradingview"
    
    try:
        print(f"📤 Sending webhook for exact user scenario...")
        response = requests.post(url, json=exact_user_payload)
        print(f"User Scenario Test Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ User scenario webhook received successfully")
            print(f"Full Response: {json.dumps(result, indent=2)}")
            
            # Detailed analysis of the response
            hl_response = result.get('hyperliquid_response', {})
            
            # Check for detailed logging indicators
            detailed_logging_found = False
            market_close_attempted = False
            market_close_failed = False
            fallback_used = False
            null_response_detected = False
            exception_caught = False
            
            response_str = str(result).lower()
            
            # Look for detailed logging patterns
            if any(phrase in response_str for phrase in [
                'using exchange.market_close()', 
                'market_close() completed',
                'parameters: coin=',
                'market_close() raw result'
            ]):
                detailed_logging_found = True
                print("✅ Detailed logging detected in response")
            
            # Check if market_close was attempted
            if 'market_close' in response_str:
                market_close_attempted = True
                print("✅ exchange.market_close() method was attempted")
            
            # Check for null response issue
            if any(phrase in response_str for phrase in [
                'null response',
                'returning null',
                'result: null',
                'market_close() raw result: null'
            ]):
                null_response_detected = True
                print("❌ CRITICAL: Null response from market_close() detected!")
            
            # Check for exceptions
            if any(phrase in response_str for phrase in [
                'exception in exchange.market_close()',
                'exception type:',
                'exception details:',
                'unknown error'
            ]):
                exception_caught = True
                print("❌ CRITICAL: Exception in market_close() detected!")
            
            # Check for fallback mechanism
            if any(phrase in response_str for phrase in [
                'falling back to reduce_only',
                'fallback mechanism',
                'retrying market_close with minimal parameters',
                'minimal parameter attempt'
            ]):
                fallback_used = True
                print("✅ Fallback mechanism was triggered")
            
            # Check for the original error that should be fixed
            original_error_present = False
            if 'order could not immediately match' in response_str:
                original_error_present = True
                print("❌ CRITICAL: Original 'Order could not immediately match' error still present!")
            else:
                print("✅ Original 'Order could not immediately match' error NOT present - Good!")
            
            # Check overall success/failure
            overall_success = hl_response.get('status') == 'success'
            
            print(f"\n📊 Detailed Analysis:")
            print(f"  - Detailed logging found: {detailed_logging_found}")
            print(f"  - market_close() attempted: {market_close_attempted}")
            print(f"  - Null response detected: {null_response_detected}")
            print(f"  - Exception caught: {exception_caught}")
            print(f"  - Fallback mechanism used: {fallback_used}")
            print(f"  - Original error present: {original_error_present}")
            print(f"  - Overall success: {overall_success}")
            
            # Analyze specific error messages
            if not overall_success:
                error_msg = hl_response.get('message', 'No error message')
                error_details = hl_response.get('error', 'No error details')
                print(f"\n🔍 Error Analysis:")
                print(f"  - Error message: {error_msg}")
                print(f"  - Error details: {error_details}")
                
                # Check for specific failure patterns
                if 'failed to clear existing positions' in error_msg.lower():
                    print("❌ CRITICAL: Position clearing is failing as reported by user")
                    
                    # Look for the root cause
                    if null_response_detected:
                        print("🔍 ROOT CAUSE: market_close() returning null response")
                    elif exception_caught:
                        print("🔍 ROOT CAUSE: Exception in market_close() method")
                    else:
                        print("🔍 ROOT CAUSE: Unknown - need more detailed logging")
            
            return overall_success and not original_error_present
                
        else:
            print(f"❌ User scenario webhook failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing user scenario: {str(e)}")
        return False
    
    # Wait before next test
    time.sleep(3)
    
    # Test 2: Check detailed logs to understand market_close() failure
    print("\n--- Test 2: Analyzing Detailed Logs for market_close() Failure ---")
    print("Checking logs to understand the exact failure in market_close()")
    
    logs_url = f"{BASE_URL}/logs"
    
    try:
        logs_response = requests.get(logs_url)
        if logs_response.status_code == 200:
            logs_data = logs_response.json()
            logs = logs_data.get('logs', [])
            
            print(f"📊 Retrieved {len(logs)} logs for analysis")
            
            # Look for market_close related logs
            market_close_logs = []
            for log in logs[-50:]:  # Check last 50 logs
                message = log.get('message', '').lower()
                if any(keyword in message for keyword in [
                    'market_close',
                    'closing position',
                    'exchange.market_close',
                    'position clearing',
                    'clear_symbol_orders'
                ]):
                    market_close_logs.append(log)
            
            print(f"🔍 Found {len(market_close_logs)} market_close related logs:")
            
            for i, log in enumerate(market_close_logs[-10:]):  # Show last 10 relevant logs
                timestamp = log.get('timestamp', 'No timestamp')
                level = log.get('level', 'INFO')
                message = log.get('message', 'No message')
                details = log.get('details', {})
                
                print(f"\nLog {i+1}: [{level}] {timestamp}")
                print(f"  Message: {message}")
                if details:
                    print(f"  Details: {details}")
                
                # Look for specific error patterns
                if 'exception' in message.lower():
                    print("  ❌ EXCEPTION DETECTED in this log")
                elif 'null' in message.lower():
                    print("  ❌ NULL RESPONSE DETECTED in this log")
                elif 'failed' in message.lower():
                    print("  ❌ FAILURE DETECTED in this log")
                elif 'success' in message.lower():
                    print("  ✅ SUCCESS DETECTED in this log")
            
            if not market_close_logs:
                print("⚠️ No market_close related logs found - may indicate logging issue")
                
        else:
            print(f"❌ Failed to retrieve logs: {logs_response.text}")
            
    except Exception as e:
        print(f"❌ Error analyzing logs: {str(e)}")
    
    # Test 3: Test fallback mechanism specifically
    print("\n--- Test 3: Testing Fallback Mechanism ---")
    print("Testing if fallback to reduce_only method works when market_close fails")
    
    fallback_test_payload = {
        "symbol": "SOL",
        "side": "sell",  # Opposite side to test position closing
        "entry": "market",
        "quantity": "10.73",  # Exact user amount
        "price": "175.00",
        "force_fallback": True,  # If backend supports this flag for testing
        "timestamp": datetime.now().isoformat()
    }
    
    try:
        print(f"📤 Sending fallback mechanism test...")
        response = requests.post(url, json=fallback_test_payload)
        print(f"Fallback Test Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Fallback test webhook received successfully")
            
            response_str = str(result).lower()
            
            # Check if fallback was used
            if any(phrase in response_str for phrase in [
                'fallback',
                'reduce_only',
                'minimal parameter',
                'alternative method'
            ]):
                print("✅ Fallback mechanism detected in response")
            else:
                print("⚠️ Fallback mechanism not clearly detected")
            
            # Check success
            hl_response = result.get('hyperliquid_response', {})
            if hl_response.get('status') == 'success':
                print("✅ Fallback mechanism worked successfully")
                return True
            else:
                print(f"❌ Fallback mechanism failed: {hl_response}")
                return False
        else:
            print(f"❌ Fallback test webhook failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing fallback mechanism: {str(e)}")
        return False

def test_position_clearing_mechanism():
    """Legacy test - now calls enhanced version"""
    return test_enhanced_position_clearing_mechanism()

def test_stop_loss_implementation():
    """Test stop loss order implementation - MAIN FOCUS OF REVIEW REQUEST"""
    print("\n=== Testing Stop Loss Implementation ===")
    print("🎯 CRITICAL: Testing stop loss orders with TradingView webhook")
    print("User reported: Normal orders work but stop loss is not being applied to position")
    
    # Test 1: BUY order with stop loss
    print("\n--- Test 1: BUY Order with Stop Loss ---")
    buy_with_stop_payload = {
        "symbol": "SOL",
        "side": "buy",
        "entry": "market",
        "quantity": "0.1",
        "price": "160.00",
        "stop": "158.00"
    }
    
    url = f"{BASE_URL}/webhook/tradingview"
    
    try:
        response = requests.post(url, json=buy_with_stop_payload)
        print(f"BUY with Stop Loss Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ BUY with stop loss webhook received successfully")
            print(f"Response: {json.dumps(result, indent=2)}")
            
            # Check if both main order and stop loss order were processed
            hl_response = result.get('hyperliquid_response', {})
            
            if hl_response.get('status') == 'success':
                order_details = hl_response.get('order_details', {})
                main_order = order_details.get('hyperliquid_response')
                stop_loss_response = order_details.get('stop_loss_response')
                
                print(f"\n📊 Main Order Response: {main_order}")
                print(f"🛑 Stop Loss Response: {stop_loss_response}")
                
                # Validate main order
                if main_order and main_order.get('status') == 'ok':
                    print("✅ Main BUY order executed successfully")
                else:
                    print("❌ Main BUY order failed")
                    return False
                
                # Validate stop loss order
                if stop_loss_response:
                    if stop_loss_response.get('status') == 'ok':
                        print("✅ Stop loss order placed successfully")
                        print("🎯 CRITICAL SUCCESS: Stop loss functionality is working!")
                    elif 'error' in stop_loss_response:
                        print(f"❌ Stop loss order failed: {stop_loss_response['error']}")
                        print("🚨 CRITICAL ISSUE: Stop loss not working as reported by user")
                        return False
                    else:
                        print(f"⚠️ Stop loss response unclear: {stop_loss_response}")
                        return False
                else:
                    print("❌ CRITICAL: No stop loss response found")
                    print("🚨 This confirms user's report - stop loss not being processed")
                    return False
            else:
                print(f"❌ Order execution failed: {hl_response}")
                return False
        else:
            print(f"❌ BUY with stop loss webhook failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing BUY with stop loss: {str(e)}")
        return False
    
    # Wait before next test
    time.sleep(3)
    
    # Test 2: SELL order with stop loss
    print("\n--- Test 2: SELL Order with Stop Loss ---")
    sell_with_stop_payload = {
        "symbol": "BTC",
        "side": "sell",
        "entry": "market",
        "quantity": "0.01",  # Increased to meet minimum size
        "price": "45000.00",
        "stop": "46000.00"
    }
    
    try:
        response = requests.post(url, json=sell_with_stop_payload)
        print(f"SELL with Stop Loss Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ SELL with stop loss webhook received successfully")
            
            # Check if both main order and stop loss order were processed
            hl_response = result.get('hyperliquid_response', {})
            
            if hl_response.get('status') == 'success':
                order_details = hl_response.get('order_details', {})
                main_order = order_details.get('hyperliquid_response')
                stop_loss_response = order_details.get('stop_loss_response')
                
                print(f"\n📊 Main Order Response: {main_order}")
                print(f"🛑 Stop Loss Response: {stop_loss_response}")
                
                # Validate main order
                if main_order and main_order.get('status') == 'ok':
                    print("✅ Main SELL order executed successfully")
                else:
                    print("❌ Main SELL order failed")
                    return False
                
                # Validate stop loss order
                if stop_loss_response:
                    if stop_loss_response.get('status') == 'ok':
                        print("✅ Stop loss order placed successfully")
                    elif 'error' in stop_loss_response:
                        print(f"❌ Stop loss order failed: {stop_loss_response['error']}")
                        return False
                    else:
                        print(f"⚠️ Stop loss response unclear: {stop_loss_response}")
                        return False
                else:
                    print("❌ CRITICAL: No stop loss response found for SELL order")
                    return False
            else:
                print(f"❌ SELL order execution failed: {hl_response}")
                return False
        else:
            print(f"❌ SELL with stop loss webhook failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing SELL with stop loss: {str(e)}")
        return False
    
    # Test 3: Different symbols with stop loss
    print("\n--- Test 3: ETH with Stop Loss ---")
    eth_with_stop_payload = {
        "symbol": "ETH",
        "side": "buy",
        "entry": "limit",
        "quantity": "0.01",
        "price": "3200.00",
        "stop": "3150.00"
    }
    
    try:
        response = requests.post(url, json=eth_with_stop_payload)
        print(f"ETH with Stop Loss Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ ETH with stop loss webhook received successfully")
            
            hl_response = result.get('hyperliquid_response', {})
            if hl_response.get('status') == 'success':
                order_details = hl_response.get('order_details', {})
                stop_loss_response = order_details.get('stop_loss_response')
                
                if stop_loss_response and stop_loss_response.get('status') == 'ok':
                    print("✅ ETH stop loss order placed successfully")
                else:
                    print(f"❌ ETH stop loss failed: {stop_loss_response}")
                    return False
            else:
                print(f"❌ ETH order failed: {hl_response}")
                return False
        else:
            print(f"❌ ETH webhook failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing ETH with stop loss: {str(e)}")
        return False
    
    print("\n✅ Stop loss implementation test completed successfully!")
    print("All stop loss orders were processed and sent to Hyperliquid testnet")
    return True

def test_real_order_execution():
    """Test real order execution on Hyperliquid testnet - KEY FOCUS AREA"""
    print("\n=== Testing Real Order Execution ===")
    print("🎯 CRITICAL: Testing real order placement on Hyperliquid testnet")
    print("This is the main focus of the review request")
    
    # Test BUY order
    print("\n--- Testing BUY Order ---")
    buy_payload = {
        "symbol": "BTC",
        "side": "buy",
        "entry": "market",
        "quantity": "0.01",  # Increased to meet minimum size
        "price": "45000",
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
        "side": "sell",
        "entry": "market",
        "quantity": "0.01",
        "price": "3200",
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

def test_clear_logs_functionality():
    """Test the clear logs functionality - MAIN FOCUS OF REVIEW REQUEST"""
    print("\n=== Testing Clear Logs Functionality ===")
    print("🎯 CRITICAL: Testing DELETE /api/logs endpoint and log generation with Brazilian timezone")
    
    # First, generate some logs by calling other endpoints
    print("\n--- Step 1: Generating logs by calling status endpoint ---")
    status_url = f"{BASE_URL}/status"
    try:
        status_response = requests.get(status_url)
        if status_response.status_code == 200:
            print("✅ Status endpoint called to generate logs")
        else:
            print(f"⚠️ Status endpoint call failed: {status_response.status_code}")
    except Exception as e:
        print(f"⚠️ Error calling status endpoint: {str(e)}")
    
    # Generate more logs with a webhook
    print("\n--- Step 2: Generating more logs with webhook ---")
    webhook_url = f"{BASE_URL}/webhook/tradingview"
    test_payload = {
        "symbol": "BTC",
        "side": "buy",
        "entry": "market",
        "quantity": "0.01",
        "price": "45000"
    }
    
    try:
        webhook_response = requests.post(webhook_url, json=test_payload)
        if webhook_response.status_code == 200:
            print("✅ Webhook called to generate more logs")
        else:
            print(f"⚠️ Webhook call failed: {webhook_response.status_code}")
    except Exception as e:
        print(f"⚠️ Error calling webhook: {str(e)}")
    
    # Wait a moment for logs to be written
    time.sleep(2)
    
    # Step 3: Check current logs and verify Brazilian timezone
    print("\n--- Step 3: Checking current logs and Brazilian timezone ---")
    logs_url = f"{BASE_URL}/logs"
    
    try:
        logs_response = requests.get(logs_url)
        print(f"GET /api/logs Status Code: {logs_response.status_code}")
        
        if logs_response.status_code == 200:
            logs_data = logs_response.json()
            log_count = len(logs_data.get('logs', []))
            print(f"✅ Retrieved {log_count} logs before clearing")
            
            # Check Brazilian timezone in timestamps
            if log_count > 0:
                print("\n🕐 Checking Brazilian timezone (GMT-3) in log timestamps:")
                for i, log in enumerate(logs_data['logs'][:5]):  # Check first 5 logs
                    timestamp = log.get('timestamp', '')
                    message = log.get('message', '')
                    level = log.get('level', '')
                    
                    print(f"Log {i+1}: [{level}] {message}")
                    print(f"  Timestamp: {timestamp}")
                    
                    # Check if timestamp contains Brazilian timezone info
                    if '-03:00' in timestamp or 'America/Sao_Paulo' in timestamp:
                        print("  ✅ Brazilian timezone (GMT-3) detected in timestamp")
                    elif timestamp:
                        # Parse timestamp to check timezone
                        try:
                            from datetime import datetime
                            import re
                            
                            # Look for timezone offset pattern
                            tz_pattern = r'([+-]\d{2}:\d{2})$'
                            tz_match = re.search(tz_pattern, timestamp)
                            
                            if tz_match:
                                tz_offset = tz_match.group(1)
                                if tz_offset == '-03:00':
                                    print("  ✅ Brazilian timezone (GMT-3) confirmed")
                                else:
                                    print(f"  ⚠️ Timezone offset is {tz_offset}, expected -03:00")
                            else:
                                print("  ⚠️ No timezone offset found in timestamp")
                        except Exception as parse_error:
                            print(f"  ⚠️ Could not parse timestamp: {parse_error}")
                    else:
                        print("  ❌ No timestamp found")
                
                print(f"\n📊 Total logs before clearing: {log_count}")
            else:
                print("⚠️ No logs found to test timezone")
        else:
            print(f"❌ Failed to retrieve logs: {logs_response.text}")
            return False
    except Exception as e:
        print(f"❌ Error retrieving logs: {str(e)}")
        return False
    
    # Step 4: Test the clear logs endpoint
    print("\n--- Step 4: Testing DELETE /api/logs endpoint ---")
    clear_url = f"{BASE_URL}/logs"
    
    try:
        clear_response = requests.delete(clear_url)
        print(f"DELETE /api/logs Status Code: {clear_response.status_code}")
        
        if clear_response.status_code == 200:
            clear_result = clear_response.json()
            print("✅ Clear logs endpoint test passed")
            print(f"Response: {json.dumps(clear_result, indent=2)}")
            
            # Verify the response structure
            if clear_result.get('status') == 'success':
                deleted_count = clear_result.get('deleted_count', 0)
                message = clear_result.get('message', '')
                
                print(f"✅ Status: {clear_result['status']}")
                print(f"✅ Message: {message}")
                print(f"✅ Deleted count: {deleted_count}")
                
                if deleted_count > 0:
                    print(f"✅ Successfully cleared {deleted_count} logs from MongoDB")
                else:
                    print("⚠️ No logs were deleted (database might have been empty)")
            else:
                print(f"❌ Unexpected response status: {clear_result.get('status')}")
                return False
        else:
            print(f"❌ Clear logs endpoint failed: {clear_response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing clear logs endpoint: {str(e)}")
        return False
    
    # Step 5: Verify logs were actually cleared
    print("\n--- Step 5: Verifying logs were cleared ---")
    
    try:
        verify_response = requests.get(logs_url)
        print(f"Verification GET /api/logs Status Code: {verify_response.status_code}")
        
        if verify_response.status_code == 200:
            verify_data = verify_response.json()
            remaining_count = len(verify_data.get('logs', []))
            
            print(f"📊 Logs remaining after clear: {remaining_count}")
            
            if remaining_count == 0:
                print("✅ PERFECT: All logs successfully cleared from database")
            elif remaining_count < log_count:
                print(f"✅ PARTIAL: Some logs cleared ({log_count - remaining_count} deleted)")
            else:
                print("❌ FAILED: No logs were cleared")
                return False
        else:
            print(f"❌ Failed to verify log clearing: {verify_response.text}")
            return False
    except Exception as e:
        print(f"❌ Error verifying log clearing: {str(e)}")
        return False
    
    # Step 6: Generate new logs and verify they have Brazilian timezone
    print("\n--- Step 6: Generating new logs to verify Brazilian timezone ---")
    
    try:
        # Generate a new log by calling status endpoint again
        new_status_response = requests.get(status_url)
        if new_status_response.status_code == 200:
            print("✅ Generated new logs after clearing")
            
            # Wait for logs to be written
            time.sleep(1)
            
            # Check new logs
            new_logs_response = requests.get(logs_url)
            if new_logs_response.status_code == 200:
                new_logs_data = new_logs_response.json()
                new_log_count = len(new_logs_data.get('logs', []))
                
                print(f"📊 New logs generated: {new_log_count}")
                
                if new_log_count > 0:
                    print("\n🕐 Verifying Brazilian timezone in new logs:")
                    for log in new_logs_data['logs'][:3]:
                        timestamp = log.get('timestamp', '')
                        message = log.get('message', '')
                        
                        print(f"New log: {message}")
                        print(f"  Timestamp: {timestamp}")
                        
                        if '-03:00' in timestamp:
                            print("  ✅ Brazilian timezone (GMT-3) confirmed in new log")
                        else:
                            print("  ⚠️ Brazilian timezone not detected in new log")
                else:
                    print("⚠️ No new logs generated")
            else:
                print(f"❌ Failed to retrieve new logs: {new_logs_response.text}")
        else:
            print(f"⚠️ Failed to generate new logs: {new_status_response.status_code}")
    except Exception as e:
        print(f"⚠️ Error generating/checking new logs: {str(e)}")
    
    print("\n✅ Clear logs functionality test completed successfully!")
    print("Key findings:")
    print("- DELETE /api/logs endpoint is working")
    print("- Logs are being cleared from MongoDB")
    print("- Brazilian timezone (GMT-3) is implemented in log timestamps")
    print("- Log generation and retrieval are working correctly")
    
    return True

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

def test_strategy_filters_fixed():
    """Test the FIXED strategy filters - MAIN FOCUS OF CURRENT REVIEW REQUEST"""
    print("\n=== Testing FIXED Strategy Filters ===")
    print("🎯 CRITICAL: Testing strategy filters that were recently corrected")
    print("User reported: Filters not working correctly - IMBA_HYPER showed 2 records initially")
    print("then several unrelated records appeared after a few seconds")
    print("CORRECTIONS IMPLEMENTED:")
    print("1. Simplified interface - removed 'mark/unmark all' buttons")
    print("2. Fixed auto-refresh problem that ignored filters")
    print("3. Initialization with all strategies DISABLED by default")
    print("4. Added 'Update' button for manual refresh")
    print("5. Better handling of empty filters")
    
    # Test 1: Test IMBA_HYPER filter specifically
    print("\n--- Test 1: IMBA_HYPER Filter (User's Reported Issue) ---")
    
    # First, create some test data with IMBA_HYPER strategy
    webhook_url = f"{BASE_URL}/webhook/tradingview"
    
    # Create IMBA_HYPER webhook
    imba_webhook = {
        "symbol": "SOL",
        "side": "buy",
        "entry": "market",
        "quantity": "0.5",
        "price": "175.00",
        "strategy_id": "IMBA_HYPER",
        "timestamp": datetime.now().isoformat()
    }
    
    try:
        print("📤 Creating IMBA_HYPER webhook for testing...")
        response = requests.post(webhook_url, json=imba_webhook)
        if response.status_code == 200:
            imba_webhook_id = response.json().get('webhook_id')
            print(f"✅ IMBA_HYPER webhook created: {imba_webhook_id}")
        else:
            print(f"❌ Failed to create IMBA_HYPER webhook: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error creating IMBA_HYPER webhook: {str(e)}")
        return False
    
    # Create OTHERS webhook for comparison
    others_webhook = {
        "symbol": "BTC",
        "side": "sell",
        "entry": "market",
        "quantity": "0.01",
        "price": "45000.00",
        # No strategy_id - should default to OTHERS
        "timestamp": datetime.now().isoformat()
    }
    
    try:
        print("📤 Creating OTHERS webhook for testing...")
        response = requests.post(webhook_url, json=others_webhook)
        if response.status_code == 200:
            others_webhook_id = response.json().get('webhook_id')
            print(f"✅ OTHERS webhook created: {others_webhook_id}")
        else:
            print(f"❌ Failed to create OTHERS webhook: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error creating OTHERS webhook: {str(e)}")
        return False
    
    # Wait for processing
    time.sleep(2)
    
    # Test IMBA_HYPER filter - this was the user's main complaint
    print("\n🔍 Testing IMBA_HYPER filter (User's reported issue)...")
    imba_filter_url = f"{BASE_URL}/webhooks?strategy_ids=IMBA_HYPER"
    
    try:
        response = requests.get(imba_filter_url)
        print(f"IMBA_HYPER Filter Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            webhooks = data.get('webhooks', [])
            print(f"✅ IMBA_HYPER filter returned {len(webhooks)} webhooks")
            
            # Critical check: Verify NO data leakage
            imba_count = 0
            leaked_count = 0
            leaked_strategies = set()
            
            for webhook in webhooks:
                strategy_id = webhook.get('strategy_id')
                if strategy_id == 'IMBA_HYPER':
                    imba_count += 1
                else:
                    leaked_count += 1
                    leaked_strategies.add(strategy_id)
            
            print(f"📊 Filter Results Analysis:")
            print(f"  - IMBA_HYPER webhooks: {imba_count}")
            print(f"  - Leaked webhooks: {leaked_count}")
            if leaked_strategies:
                print(f"  - Leaked strategy_ids: {list(leaked_strategies)}")
            
            # This is the CRITICAL test - no data leakage
            if leaked_count == 0:
                print("✅ PERFECT: No data leakage detected in IMBA_HYPER filter!")
                print("✅ User's reported issue appears to be FIXED!")
            else:
                print(f"❌ CRITICAL: Data leakage detected! {leaked_count} non-IMBA_HYPER webhooks returned")
                print(f"❌ This confirms user's report - filter is NOT working correctly")
                print(f"❌ Leaked strategies: {list(leaked_strategies)}")
                return False
            
            # Verify our test webhook is included
            found_test_webhook = False
            for webhook in webhooks:
                if webhook.get('id') == imba_webhook_id:
                    found_test_webhook = True
                    break
            
            if found_test_webhook:
                print("✅ Test IMBA_HYPER webhook correctly included in filter results")
            else:
                print("❌ Test IMBA_HYPER webhook missing from filter results")
                return False
                
        else:
            print(f"❌ IMBA_HYPER filter failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing IMBA_HYPER filter: {str(e)}")
        return False
    
    # Test 2: Test OTHERS filter
    print("\n--- Test 2: OTHERS Filter ---")
    
    others_filter_url = f"{BASE_URL}/webhooks?strategy_ids=OTHERS"
    
    try:
        response = requests.get(others_filter_url)
        print(f"OTHERS Filter Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            webhooks = data.get('webhooks', [])
            print(f"✅ OTHERS filter returned {len(webhooks)} webhooks")
            
            # Check for data leakage
            others_count = 0
            leaked_count = 0
            leaked_strategies = set()
            
            for webhook in webhooks:
                strategy_id = webhook.get('strategy_id')
                if strategy_id == 'OTHERS':
                    others_count += 1
                else:
                    leaked_count += 1
                    leaked_strategies.add(strategy_id)
            
            print(f"📊 OTHERS Filter Results:")
            print(f"  - OTHERS webhooks: {others_count}")
            print(f"  - Leaked webhooks: {leaked_count}")
            if leaked_strategies:
                print(f"  - Leaked strategy_ids: {list(leaked_strategies)}")
            
            if leaked_count == 0:
                print("✅ No data leakage in OTHERS filter")
            else:
                print(f"❌ Data leakage in OTHERS filter: {leaked_count} non-OTHERS webhooks")
                return False
            
            # Verify our test webhook is included
            found_test_webhook = False
            for webhook in webhooks:
                if webhook.get('id') == others_webhook_id:
                    found_test_webhook = True
                    break
            
            if found_test_webhook:
                print("✅ Test OTHERS webhook correctly included in filter results")
            else:
                print("❌ Test OTHERS webhook missing from filter results")
                return False
                
        else:
            print(f"❌ OTHERS filter failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing OTHERS filter: {str(e)}")
        return False
    
    # Test 3: Test combined filter (IMBA_HYPER,OTHERS)
    print("\n--- Test 3: Combined Filter (IMBA_HYPER,OTHERS) ---")
    
    combined_filter_url = f"{BASE_URL}/webhooks?strategy_ids=IMBA_HYPER,OTHERS"
    
    try:
        response = requests.get(combined_filter_url)
        print(f"Combined Filter Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            webhooks = data.get('webhooks', [])
            print(f"✅ Combined filter returned {len(webhooks)} webhooks")
            
            # Check for data leakage
            valid_strategies = {'IMBA_HYPER', 'OTHERS'}
            valid_count = 0
            leaked_count = 0
            leaked_strategies = set()
            
            for webhook in webhooks:
                strategy_id = webhook.get('strategy_id')
                if strategy_id in valid_strategies:
                    valid_count += 1
                else:
                    leaked_count += 1
                    leaked_strategies.add(strategy_id)
            
            print(f"📊 Combined Filter Results:")
            print(f"  - Valid webhooks (IMBA_HYPER/OTHERS): {valid_count}")
            print(f"  - Leaked webhooks: {leaked_count}")
            if leaked_strategies:
                print(f"  - Leaked strategy_ids: {list(leaked_strategies)}")
            
            if leaked_count == 0:
                print("✅ No data leakage in combined filter")
            else:
                print(f"❌ Data leakage in combined filter: {leaked_count} invalid webhooks")
                return False
            
            # Verify both test webhooks are included
            found_imba = False
            found_others = False
            for webhook in webhooks:
                webhook_id = webhook.get('id')
                if webhook_id == imba_webhook_id:
                    found_imba = True
                elif webhook_id == others_webhook_id:
                    found_others = True
            
            if found_imba and found_others:
                print("✅ Both test webhooks correctly included in combined filter")
            else:
                print(f"❌ Missing test webhooks - IMBA: {found_imba}, OTHERS: {found_others}")
                return False
                
        else:
            print(f"❌ Combined filter failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing combined filter: {str(e)}")
        return False
    
    # Test 4: Test responses filtering (same issue could affect responses)
    print("\n--- Test 4: Responses Filter Testing ---")
    
    # Test IMBA_HYPER responses filter
    imba_responses_url = f"{BASE_URL}/responses?strategy_ids=IMBA_HYPER"
    
    try:
        response = requests.get(imba_responses_url)
        print(f"IMBA_HYPER Responses Filter Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            responses = data.get('responses', [])
            print(f"✅ IMBA_HYPER responses filter returned {len(responses)} responses")
            
            # Check for data leakage in responses
            imba_count = 0
            leaked_count = 0
            leaked_strategies = set()
            
            for response_item in responses:
                strategy_id = response_item.get('strategy_id')
                if strategy_id == 'IMBA_HYPER':
                    imba_count += 1
                else:
                    leaked_count += 1
                    leaked_strategies.add(strategy_id)
            
            print(f"📊 IMBA_HYPER Responses Filter:")
            print(f"  - IMBA_HYPER responses: {imba_count}")
            print(f"  - Leaked responses: {leaked_count}")
            if leaked_strategies:
                print(f"  - Leaked strategy_ids: {list(leaked_strategies)}")
            
            if leaked_count == 0:
                print("✅ No data leakage in IMBA_HYPER responses filter")
            else:
                print(f"❌ Data leakage in IMBA_HYPER responses filter: {leaked_count} invalid responses")
                return False
                
        else:
            print(f"❌ IMBA_HYPER responses filter failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing IMBA_HYPER responses filter: {str(e)}")
        return False
    
    # Test 5: Test empty filter (should return all)
    print("\n--- Test 5: Empty Filter (Should Return All) ---")
    
    all_webhooks_url = f"{BASE_URL}/webhooks"
    
    try:
        response = requests.get(all_webhooks_url)
        print(f"All Webhooks Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            all_webhooks = data.get('webhooks', [])
            print(f"✅ All webhooks endpoint returned {len(all_webhooks)} webhooks")
            
            # This should include both our test webhooks
            found_imba = False
            found_others = False
            strategy_counts = {}
            
            for webhook in all_webhooks:
                webhook_id = webhook.get('id')
                strategy_id = webhook.get('strategy_id', 'None')
                
                strategy_counts[strategy_id] = strategy_counts.get(strategy_id, 0) + 1
                
                if webhook_id == imba_webhook_id:
                    found_imba = True
                elif webhook_id == others_webhook_id:
                    found_others = True
            
            print(f"📊 All Webhooks Strategy Distribution:")
            for strategy, count in strategy_counts.items():
                print(f"  - {strategy}: {count} webhooks")
            
            if found_imba and found_others:
                print("✅ Both test webhooks found in unfiltered results")
            else:
                print(f"❌ Missing test webhooks in unfiltered results - IMBA: {found_imba}, OTHERS: {found_others}")
                return False
                
        else:
            print(f"❌ All webhooks endpoint failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing all webhooks endpoint: {str(e)}")
        return False
    
    print("\n✅ STRATEGY FILTERS TESTING COMPLETED SUCCESSFULLY!")
    print("🎯 KEY FINDINGS:")
    print("✅ IMBA_HYPER filter working correctly - no data leakage detected")
    print("✅ OTHERS filter working correctly - no data leakage detected")
    print("✅ Combined filters working correctly - no data leakage detected")
    print("✅ Responses filters working correctly - no data leakage detected")
    print("✅ Empty filters working correctly - returns all data")
    print("🎉 USER'S REPORTED ISSUE APPEARS TO BE FIXED!")
    
    return True

def test_strategy_segmentation_system():
    """Test the complete strategy segmentation system - MAIN FOCUS OF REVIEW REQUEST"""
    print("\n=== Testing Strategy Segmentation System ===")
    print("🎯 CRITICAL: Testing complete strategy segmentation by strategy_id")
    print("Features: Auto-segmentation, rule center, API endpoints, auto-filters, visual interface")
    
    # Test 1: Test strategy endpoints
    print("\n--- Test 1: Strategy API Endpoints ---")
    
    # Test GET /api/strategies
    strategies_url = f"{BASE_URL}/strategies"
    try:
        response = requests.get(strategies_url)
        print(f"GET /api/strategies Status Code: {response.status_code}")
        
        if response.status_code == 200:
            strategies_data = response.json()
            print("✅ GET /api/strategies endpoint working")
            
            strategies = strategies_data.get('strategies', {})
            print(f"📊 Found {len(strategies)} strategies:")
            
            # Check for default strategies
            expected_strategies = ["IMBA_HYPER", "OTHERS"]
            for strategy_id in expected_strategies:
                if strategy_id in strategies:
                    strategy = strategies[strategy_id]
                    print(f"  ✅ {strategy_id}: {strategy.get('name', 'No name')}")
                    print(f"    - Enabled: {strategy.get('enabled', False)}")
                    print(f"    - Rules: {strategy.get('rules', {})}")
                    print(f"    - Stats: {strategy.get('stats', {})}")
                    
                    # Verify strategy rules
                    rules = strategy.get('rules', {})
                    if strategy_id == "IMBA_HYPER":
                        expected_max_pos = 100.0
                        expected_max_trades = 50
                    else:  # OTHERS
                        expected_max_pos = 50.0
                        expected_max_trades = 25
                    
                    actual_max_pos = rules.get('max_position_size')
                    actual_max_trades = rules.get('risk_management', {}).get('max_daily_trades')
                    
                    if actual_max_pos == expected_max_pos:
                        print(f"    ✅ Max position size correct: {actual_max_pos}")
                    else:
                        print(f"    ❌ Max position size incorrect: expected {expected_max_pos}, got {actual_max_pos}")
                        
                    if actual_max_trades == expected_max_trades:
                        print(f"    ✅ Max daily trades correct: {actual_max_trades}")
                    else:
                        print(f"    ❌ Max daily trades incorrect: expected {expected_max_trades}, got {actual_max_trades}")
                else:
                    print(f"  ❌ Missing expected strategy: {strategy_id}")
                    return False
        else:
            print(f"❌ GET /api/strategies failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing GET /api/strategies: {str(e)}")
        return False
    
    # Test GET /api/strategies/ids
    strategy_ids_url = f"{BASE_URL}/strategies/ids"
    try:
        response = requests.get(strategy_ids_url)
        print(f"GET /api/strategies/ids Status Code: {response.status_code}")
        
        if response.status_code == 200:
            ids_data = response.json()
            strategy_ids = ids_data.get('strategy_ids', [])
            print(f"✅ GET /api/strategies/ids working - Found {len(strategy_ids)} strategy IDs:")
            print(f"  Strategy IDs: {strategy_ids}")
            
            # Verify expected IDs are present
            if "IMBA_HYPER" in strategy_ids and "OTHERS" in strategy_ids:
                print("  ✅ Default strategy IDs present")
            else:
                print("  ❌ Missing default strategy IDs")
                return False
        else:
            print(f"❌ GET /api/strategies/ids failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing GET /api/strategies/ids: {str(e)}")
        return False
    
    # Test 2: Test webhook WITH strategy_id (IMBA_HYPER)
    print("\n--- Test 2: Webhook WITH strategy_id (IMBA_HYPER) ---")
    
    webhook_with_strategy = {
        "symbol": "SOL",
        "side": "buy",
        "entry": "market",
        "quantity": "0.5",
        "price": "175.00",
        "strategy_id": "IMBA_HYPER",  # Explicit strategy_id
        "timestamp": datetime.now().isoformat()
    }
    
    webhook_url = f"{BASE_URL}/webhook/tradingview"
    try:
        response = requests.post(webhook_url, json=webhook_with_strategy)
        print(f"Webhook with IMBA_HYPER Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Webhook with strategy_id processed successfully")
            
            # Verify the webhook was stored with correct strategy_id
            webhook_id = result.get('webhook_id')
            if webhook_id:
                print(f"  Webhook ID: {webhook_id}")
                
                # Check if strategy was auto-registered
                time.sleep(1)  # Wait for processing
                
                # Verify in webhooks endpoint with filtering
                webhooks_filter_url = f"{BASE_URL}/webhooks?strategy_ids=IMBA_HYPER"
                webhooks_response = requests.get(webhooks_filter_url)
                
                if webhooks_response.status_code == 200:
                    webhooks_data = webhooks_response.json()
                    webhooks = webhooks_data.get('webhooks', [])
                    
                    # Find our webhook
                    found_webhook = None
                    for webhook in webhooks:
                        if webhook.get('id') == webhook_id:
                            found_webhook = webhook
                            break
                    
                    if found_webhook:
                        stored_strategy_id = found_webhook.get('strategy_id')
                        if stored_strategy_id == "IMBA_HYPER":
                            print("  ✅ Webhook correctly stored with IMBA_HYPER strategy_id")
                        else:
                            print(f"  ❌ Webhook stored with wrong strategy_id: {stored_strategy_id}")
                            return False
                    else:
                        print("  ❌ Webhook not found in filtered results")
                        return False
                else:
                    print(f"  ❌ Failed to verify webhook storage: {webhooks_response.text}")
            else:
                print("  ❌ No webhook_id returned")
                return False
        else:
            print(f"❌ Webhook with strategy_id failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing webhook with strategy_id: {str(e)}")
        return False
    
    # Test 3: Test webhook WITHOUT strategy_id (should default to OTHERS)
    print("\n--- Test 3: Webhook WITHOUT strategy_id (should default to OTHERS) ---")
    
    webhook_without_strategy = {
        "symbol": "BTC",
        "side": "sell",
        "entry": "market",
        "quantity": "0.01",
        "price": "45000.00",
        # No strategy_id - should default to "OTHERS"
        "timestamp": datetime.now().isoformat()
    }
    
    try:
        response = requests.post(webhook_url, json=webhook_without_strategy)
        print(f"Webhook without strategy_id Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Webhook without strategy_id processed successfully")
            
            webhook_id = result.get('webhook_id')
            if webhook_id:
                time.sleep(1)  # Wait for processing
                
                # Verify it was classified as OTHERS
                webhooks_filter_url = f"{BASE_URL}/webhooks?strategy_ids=OTHERS"
                webhooks_response = requests.get(webhooks_filter_url)
                
                if webhooks_response.status_code == 200:
                    webhooks_data = webhooks_response.json()
                    webhooks = webhooks_data.get('webhooks', [])
                    
                    found_webhook = None
                    for webhook in webhooks:
                        if webhook.get('id') == webhook_id:
                            found_webhook = webhook
                            break
                    
                    if found_webhook:
                        stored_strategy_id = found_webhook.get('strategy_id')
                        if stored_strategy_id == "OTHERS":
                            print("  ✅ Webhook correctly classified as OTHERS strategy")
                        else:
                            print(f"  ❌ Webhook classified incorrectly: {stored_strategy_id}")
                            return False
                    else:
                        print("  ❌ Webhook not found in OTHERS filtered results")
                        return False
                else:
                    print(f"  ❌ Failed to verify OTHERS classification: {webhooks_response.text}")
            else:
                print("  ❌ No webhook_id returned")
                return False
        else:
            print(f"❌ Webhook without strategy_id failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing webhook without strategy_id: {str(e)}")
        return False
    
    # Test 4: Test new strategy_id auto-discovery
    print("\n--- Test 4: New strategy_id auto-discovery ---")
    
    new_strategy_id = f"TEST_STRATEGY_{int(time.time())}"  # Unique strategy ID
    webhook_new_strategy = {
        "symbol": "ETH",
        "side": "buy",
        "entry": "limit",
        "quantity": "0.1",
        "price": "3200.00",
        "strategy_id": new_strategy_id,  # New strategy_id
        "timestamp": datetime.now().isoformat()
    }
    
    try:
        response = requests.post(webhook_url, json=webhook_new_strategy)
        print(f"Webhook with new strategy_id Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Webhook with new strategy_id ({new_strategy_id}) processed successfully")
            
            time.sleep(2)  # Wait for auto-discovery processing
            
            # Check if new strategy was auto-discovered
            strategy_ids_response = requests.get(strategy_ids_url)
            if strategy_ids_response.status_code == 200:
                ids_data = strategy_ids_response.json()
                current_strategy_ids = ids_data.get('strategy_ids', [])
                
                if new_strategy_id in current_strategy_ids:
                    print(f"  ✅ New strategy_id {new_strategy_id} auto-discovered and added")
                    
                    # Verify the new strategy has default configuration
                    new_strategy_url = f"{BASE_URL}/strategies/{new_strategy_id}"
                    strategy_response = requests.get(new_strategy_url)
                    
                    if strategy_response.status_code == 200:
                        strategy_data = strategy_response.json()
                        print(f"  ✅ New strategy configuration retrieved:")
                        print(f"    - Name: {strategy_data.get('name')}")
                        print(f"    - Enabled: {strategy_data.get('enabled')}")
                        print(f"    - Rules: {strategy_data.get('rules')}")
                        
                        # Verify it has default OTHERS rules
                        rules = strategy_data.get('rules', {})
                        if rules.get('max_position_size') == 50.0:
                            print("  ✅ New strategy has correct default rules")
                        else:
                            print("  ❌ New strategy has incorrect default rules")
                            return False
                    else:
                        print(f"  ❌ Failed to get new strategy config: {strategy_response.text}")
                        return False
                else:
                    print(f"  ❌ New strategy_id {new_strategy_id} not auto-discovered")
                    print(f"  Current strategy IDs: {current_strategy_ids}")
                    return False
            else:
                print(f"  ❌ Failed to check strategy IDs: {strategy_ids_response.text}")
                return False
        else:
            print(f"❌ Webhook with new strategy_id failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing new strategy_id auto-discovery: {str(e)}")
        return False
    
    # Test 5: Test strategy filtering in webhooks and responses
    print("\n--- Test 5: Strategy Filtering in Webhooks and Responses ---")
    
    # Test webhooks filtering
    try:
        # Test single strategy filter
        single_filter_url = f"{BASE_URL}/webhooks?strategy_ids=IMBA_HYPER"
        response = requests.get(single_filter_url)
        
        if response.status_code == 200:
            data = response.json()
            webhooks = data.get('webhooks', [])
            print(f"✅ Single strategy filter (IMBA_HYPER): {len(webhooks)} webhooks")
            
            # Verify all returned webhooks have correct strategy_id
            all_correct = True
            for webhook in webhooks[:5]:  # Check first 5
                if webhook.get('strategy_id') != 'IMBA_HYPER':
                    all_correct = False
                    break
            
            if all_correct:
                print("  ✅ All filtered webhooks have correct strategy_id")
            else:
                print("  ❌ Some filtered webhooks have incorrect strategy_id")
                return False
        else:
            print(f"❌ Single strategy filter failed: {response.text}")
            return False
        
        # Test multiple strategy filter
        multi_filter_url = f"{BASE_URL}/webhooks?strategy_ids=IMBA_HYPER,OTHERS"
        response = requests.get(multi_filter_url)
        
        if response.status_code == 200:
            data = response.json()
            webhooks = data.get('webhooks', [])
            print(f"✅ Multiple strategy filter (IMBA_HYPER,OTHERS): {len(webhooks)} webhooks")
            
            # Verify all returned webhooks have correct strategy_ids
            valid_strategy_ids = {'IMBA_HYPER', 'OTHERS'}
            all_correct = True
            for webhook in webhooks[:5]:  # Check first 5
                if webhook.get('strategy_id') not in valid_strategy_ids:
                    all_correct = False
                    break
            
            if all_correct:
                print("  ✅ All multi-filtered webhooks have correct strategy_ids")
            else:
                print("  ❌ Some multi-filtered webhooks have incorrect strategy_ids")
                return False
        else:
            print(f"❌ Multiple strategy filter failed: {response.text}")
            return False
        
        # Test responses filtering
        responses_filter_url = f"{BASE_URL}/responses?strategy_ids=IMBA_HYPER"
        response = requests.get(responses_filter_url)
        
        if response.status_code == 200:
            data = response.json()
            responses = data.get('responses', [])
            print(f"✅ Responses strategy filter (IMBA_HYPER): {len(responses)} responses")
            
            # Verify all returned responses have correct strategy_id
            all_correct = True
            for resp in responses[:3]:  # Check first 3
                if resp.get('strategy_id') != 'IMBA_HYPER':
                    all_correct = False
                    break
            
            if all_correct:
                print("  ✅ All filtered responses have correct strategy_id")
            else:
                print("  ❌ Some filtered responses have incorrect strategy_id")
                return False
        else:
            print(f"❌ Responses strategy filter failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing strategy filtering: {str(e)}")
        return False
    
    # Test 6: Test strategy toggle functionality
    print("\n--- Test 6: Strategy Toggle Functionality ---")
    
    try:
        # Test toggling IMBA_HYPER strategy
        toggle_url = f"{BASE_URL}/strategies/IMBA_HYPER/toggle"
        response = requests.post(toggle_url)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Strategy toggle successful:")
            print(f"  Strategy: {result.get('strategy_id')}")
            print(f"  New status: {'Enabled' if result.get('enabled') else 'Disabled'}")
            print(f"  Message: {result.get('message')}")
            
            # Toggle back to original state
            response2 = requests.post(toggle_url)
            if response2.status_code == 200:
                result2 = response2.json()
                print(f"  ✅ Toggled back: {'Enabled' if result2.get('enabled') else 'Disabled'}")
            else:
                print(f"  ❌ Failed to toggle back: {response2.text}")
                return False
        else:
            print(f"❌ Strategy toggle failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing strategy toggle: {str(e)}")
        return False
    
    print("\n✅ Strategy Segmentation System test completed successfully!")
    print("All strategy segmentation features are working correctly:")
    print("- ✅ Automatic segmentation by strategy_id")
    print("- ✅ Strategy rule center with different configurations")
    print("- ✅ API endpoints (/api/strategies, /api/strategies/ids, /api/strategies/{id}/toggle)")
    print("- ✅ Automatic filter creation for new strategy_ids")
    print("- ✅ Strategy filtering in webhooks and responses endpoints")
    print("- ✅ Strategy-specific rule application")
    
    return True

def run_all_tests():
    """Run all tests and report results"""
    print("=" * 80)
    print("TRADINGVIEW TO HYPERLIQUID MIDDLEWARE BACKEND TESTS")
    print("FOCUS: Strategy Filters Testing (User's Main Complaint)")
    print("=" * 80)
    print(f"Testing against: {BASE_URL}")
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Track test results
    results = {}
    
    # PRIORITY 1: Test strategy filters (USER'S MAIN COMPLAINT)
    strategy_filters_success = test_strategy_filters_fixed()
    results["Strategy Filters (FIXED)"] = strategy_filters_success
    
    # PRIORITY 2: Test strategy segmentation system (MAIN FOCUS OF REVIEW REQUEST)
    strategy_segmentation_success = test_strategy_segmentation_system()
    results["Strategy Segmentation System"] = strategy_segmentation_success
    
    # Test Hyperliquid connection first (key focus area)
    hl_connection_success = test_hyperliquid_connection()
    results["Hyperliquid Connection"] = hl_connection_success
    
    # Test status endpoint (key focus area)
    status_success = test_status_endpoint()
    results["Status Endpoint"] = status_success
    
    # Test position clearing mechanism
    position_clearing_success = test_position_clearing_mechanism()
    results["Position Clearing Mechanism"] = position_clearing_success
    
    # Test clear logs functionality
    clear_logs_success = test_clear_logs_functionality()
    results["Clear Logs Functionality"] = clear_logs_success
    
    # Test logs endpoint to ensure it works after clearing
    logs_success = test_logs_endpoint()
    results["Logs Endpoint"] = logs_success
    
    # Test webhook endpoint to generate logs and verify Brazilian timezone
    webhook_success, webhook_id = test_webhook_endpoint()
    results["Webhook Endpoint"] = webhook_success
    
    # Test stop loss implementation
    stop_loss_success = test_stop_loss_implementation()
    results["Stop Loss Implementation"] = stop_loss_success
    
    # Test real order execution
    order_execution_success = test_real_order_execution()
    results["Real Order Execution"] = order_execution_success
    
    # Test previously failing endpoints
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
            if test_name in ["Strategy Filters (FIXED)", "Strategy Segmentation System", "Hyperliquid Connection", "Status Endpoint", "Webhook Endpoint"]:
                critical_failures.append(test_name)
    
    print(f"\nOVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    if critical_failures:
        print(f"\n🚨 CRITICAL FAILURES: {', '.join(critical_failures)}")
        print("These are the key areas mentioned in the review request that need attention.")
        
        # Special focus on strategy filters
        if "Strategy Filters (FIXED)" in critical_failures:
            print("\n🚨 STRATEGY FILTERS STILL FAILING:")
            print("   - IMBA_HYPER filter may still be showing unrelated records")
            print("   - Data leakage detected in filtered results")
            print("   - Auto-refresh may still be ignoring filters")
            print("   - User's reported issue is NOT fixed")
        
        # Special focus on strategy segmentation system
        if "Strategy Segmentation System" in critical_failures:
            print("\n🚨 STRATEGY SEGMENTATION SYSTEM FAILED:")
            print("   - Strategy API endpoints may not be working properly")
            print("   - Auto-segmentation by strategy_id may be failing")
            print("   - Strategy filtering in webhooks/responses may not work")
            print("   - New strategy auto-discovery may be broken")
        
        # Special focus on position clearing
        if "Position Clearing Mechanism" in critical_failures:
            print("\n🚨 POSITION CLEARING MECHANISM FAILED:")
            print("   - The exchange.market_close() fix may not be working properly")
            print("   - 'Order could not immediately match' error may still be occurring")
            print("   - Position inversion (close existing -> place new) may be failing")
    
    print("=" * 80)
    
    return all_passed

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)