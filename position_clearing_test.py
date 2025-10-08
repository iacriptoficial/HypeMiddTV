#!/usr/bin/env python3
"""
Specific test for position clearing mechanism - CRITICAL FOCUS
Tests the exact user scenario: -10.73 SOL position clearing
"""
import requests
import json
import time
from datetime import datetime

BASE_URL = "https://strat-manager.preview.emergentagent.com/api"

def test_position_clearing_with_real_scenario():
    """Test position clearing with a real scenario that forces position clearing"""
    print("=" * 80)
    print("POSITION CLEARING MECHANISM TEST - CRITICAL FOCUS")
    print("Testing the exact user scenario: SOL position clearing")
    print("=" * 80)
    
    # Step 1: Create a position first (SHORT SOL)
    print("\n--- Step 1: Creating SHORT SOL position ---")
    short_payload = {
        "symbol": "SOL",
        "side": "sell",  # Create short position
        "entry": "market",
        "quantity": "0.5",  # Small position for testing
        "price": "180.00",
        "timestamp": datetime.now().isoformat()
    }
    
    webhook_url = f"{BASE_URL}/webhook/tradingview"
    
    try:
        print("📤 Creating SHORT position...")
        response = requests.post(webhook_url, json=short_payload)
        print(f"SHORT Position Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ SHORT position created successfully")
            
            # Extract order details
            hl_response = result.get('hyperliquid_response', {})
            if hl_response.get('status') == 'success':
                order_details = hl_response.get('order_details', {})
                hl_result = order_details.get('hyperliquid_response', {})
                
                if hl_result.get('status') == 'ok':
                    # Look for order ID
                    response_data = hl_result.get('response', {}).get('data', {})
                    statuses = response_data.get('statuses', [])
                    
                    for status in statuses:
                        if 'filled' in status:
                            order_id = status['filled'].get('oid')
                            avg_price = status['filled'].get('avgPx')
                            total_size = status['filled'].get('totalSz')
                            print(f"✅ SHORT Order ID: {order_id}")
                            print(f"✅ Filled at: ${avg_price}")
                            print(f"✅ Size: {total_size} SOL")
                            break
                else:
                    print(f"❌ SHORT order failed: {hl_result}")
                    return False
            else:
                print(f"❌ SHORT position creation failed: {hl_response}")
                return False
        else:
            print(f"❌ SHORT position webhook failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error creating SHORT position: {str(e)}")
        return False
    
    # Wait for position to settle
    print("\n⏳ Waiting 5 seconds for position to settle...")
    time.sleep(5)
    
    # Step 2: Check current positions
    print("\n--- Step 2: Checking current positions ---")
    try:
        # Get current logs to see position status
        logs_response = requests.get(f"{BASE_URL}/logs")
        if logs_response.status_code == 200:
            logs_data = logs_response.json()
            logs = logs_data.get('logs', [])
            
            print(f"📊 Checking last 10 logs for position info:")
            for log in logs[-10:]:
                message = log.get('message', '').lower()
                if 'sol' in message and ('position' in message or 'order' in message):
                    print(f"  - {log.get('message', 'No message')}")
        else:
            print(f"⚠️ Could not retrieve logs: {logs_response.status_code}")
    except Exception as e:
        print(f"⚠️ Error checking logs: {str(e)}")
    
    # Step 3: Create opposite position that should trigger clearing
    print("\n--- Step 3: Creating BUY order to trigger position clearing ---")
    buy_payload = {
        "symbol": "SOL",
        "side": "buy",  # Opposite side - should trigger position clearing
        "entry": "market",
        "quantity": "1.0",  # Larger than existing position to force clearing + new position
        "price": "180.00",
        "timestamp": datetime.now().isoformat()
    }
    
    try:
        print("📤 Sending BUY order that should trigger position clearing...")
        print("🎯 This should call exchange.market_close() to clear the SHORT position")
        
        response = requests.post(webhook_url, json=buy_payload)
        print(f"BUY Order Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ BUY order webhook received successfully")
            print(f"Full Response: {json.dumps(result, indent=2)}")
            
            # Analyze the response for position clearing indicators
            response_str = str(result).lower()
            
            # Check for position clearing indicators
            position_clearing_detected = False
            market_close_used = False
            fallback_used = False
            clearing_failed = False
            
            # Look for position clearing patterns
            clearing_patterns = [
                'clearing all orders and positions',
                'closing position',
                'clear_symbol_orders_and_positions',
                'market_close',
                'position clearing',
                'existing positions'
            ]
            
            for pattern in clearing_patterns:
                if pattern in response_str:
                    position_clearing_detected = True
                    print(f"✅ Position clearing detected: '{pattern}' found in response")
                    break
            
            # Check for market_close usage
            if 'market_close' in response_str:
                market_close_used = True
                print("✅ exchange.market_close() method was used")
            
            # Check for fallback mechanism
            if any(phrase in response_str for phrase in ['fallback', 'reduce_only', 'minimal parameter']):
                fallback_used = True
                print("✅ Fallback mechanism was triggered")
            
            # Check for clearing failure
            if any(phrase in response_str for phrase in ['failed to clear', 'clearing failed', 'position clearing failed']):
                clearing_failed = True
                print("❌ Position clearing FAILED")
            
            # Check overall success
            hl_response = result.get('hyperliquid_response', {})
            overall_success = hl_response.get('status') == 'success'
            
            print(f"\n📊 Position Clearing Analysis:")
            print(f"  - Position clearing detected: {position_clearing_detected}")
            print(f"  - market_close() used: {market_close_used}")
            print(f"  - Fallback mechanism used: {fallback_used}")
            print(f"  - Clearing failed: {clearing_failed}")
            print(f"  - Overall success: {overall_success}")
            
            if not position_clearing_detected:
                print("⚠️ WARNING: No position clearing detected - may indicate no existing position to clear")
            
            if clearing_failed:
                print("❌ CRITICAL: Position clearing failed as reported by user")
                return False
            
            if overall_success and not clearing_failed:
                print("✅ Position clearing mechanism appears to be working")
                return True
            else:
                print("❌ Position clearing mechanism has issues")
                return False
                
        else:
            print(f"❌ BUY order webhook failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing position clearing: {str(e)}")
        return False

def analyze_recent_logs_for_position_clearing():
    """Analyze recent logs specifically for position clearing activity"""
    print("\n--- Analyzing Recent Logs for Position Clearing Activity ---")
    
    try:
        logs_response = requests.get(f"{BASE_URL}/logs")
        if logs_response.status_code == 200:
            logs_data = logs_response.json()
            logs = logs_data.get('logs', [])
            
            print(f"📊 Analyzing {len(logs)} logs for position clearing activity...")
            
            # Look for position clearing related logs
            clearing_logs = []
            for log in logs:
                message = log.get('message', '').lower()
                if any(keyword in message for keyword in [
                    'market_close',
                    'closing position',
                    'clear_symbol_orders',
                    'position clearing',
                    'exchange.market_close',
                    'fallback',
                    'reduce_only',
                    'failed to clear'
                ]):
                    clearing_logs.append(log)
            
            print(f"🔍 Found {len(clearing_logs)} position clearing related logs:")
            
            if clearing_logs:
                for i, log in enumerate(clearing_logs[-15:]):  # Show last 15 relevant logs
                    timestamp = log.get('timestamp', 'No timestamp')
                    level = log.get('level', 'INFO')
                    message = log.get('message', 'No message')
                    
                    print(f"\nClearing Log {i+1}: [{level}] {timestamp}")
                    print(f"  Message: {message}")
                    
                    # Highlight critical patterns
                    message_lower = message.lower()
                    if 'market_close' in message_lower:
                        print("  🎯 MARKET_CLOSE METHOD DETECTED")
                    if 'failed' in message_lower:
                        print("  ❌ FAILURE DETECTED")
                    if 'success' in message_lower:
                        print("  ✅ SUCCESS DETECTED")
                    if 'fallback' in message_lower:
                        print("  🔄 FALLBACK MECHANISM DETECTED")
                    if 'null' in message_lower or 'none' in message_lower:
                        print("  ⚠️ NULL/NONE RESPONSE DETECTED")
            else:
                print("⚠️ No position clearing related logs found in recent activity")
                print("This could indicate:")
                print("  - No position clearing has been attempted recently")
                print("  - Position clearing logs are not being generated properly")
                print("  - The clearing mechanism is not being triggered")
                
        else:
            print(f"❌ Failed to retrieve logs: {logs_response.status_code}")
            
    except Exception as e:
        print(f"❌ Error analyzing logs: {str(e)}")

if __name__ == "__main__":
    print("Starting targeted position clearing test...")
    
    # First analyze recent logs
    analyze_recent_logs_for_position_clearing()
    
    # Then run the position clearing test
    success = test_position_clearing_with_real_scenario()
    
    # Analyze logs again after the test
    print("\n" + "=" * 80)
    print("POST-TEST LOG ANALYSIS")
    print("=" * 80)
    analyze_recent_logs_for_position_clearing()
    
    print("\n" + "=" * 80)
    print(f"FINAL RESULT: {'✅ POSITION CLEARING WORKING' if success else '❌ POSITION CLEARING FAILED'}")
    print("=" * 80)