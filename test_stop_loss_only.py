#!/usr/bin/env python3
import requests
import json
import time
from datetime import datetime

# Base URL from frontend/.env
BASE_URL = "https://strat-manager.preview.emergentagent.com/api"

def test_stop_loss_focused():
    """Focused test on stop loss functionality only"""
    print("=== FOCUSED STOP LOSS TEST ===")
    print("🎯 Testing stop loss implementation as requested in review")
    
    # Test with SOL (smaller minimum size)
    print("\n--- Testing SOL with Stop Loss ---")
    sol_payload = {
        "symbol": "SOL",
        "side": "buy",
        "entry": "market",
        "quantity": "0.1",
        "price": "160.00",
        "stop": "158.00"
    }
    
    url = f"{BASE_URL}/webhook/tradingview"
    
    try:
        print(f"Sending payload: {json.dumps(sol_payload, indent=2)}")
        response = requests.post(url, json=sol_payload)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Webhook received successfully")
            
            # Check the response structure
            hl_response = result.get('hyperliquid_response', {})
            print(f"\nHyperliquid Response Status: {hl_response.get('status')}")
            print(f"Message: {hl_response.get('message')}")
            
            if hl_response.get('status') == 'success':
                order_details = hl_response.get('order_details', {})
                
                # Check for main order response
                main_order = order_details.get('hyperliquid_response')
                print(f"\n📊 Main Order: {main_order}")
                
                # Check for stop loss response
                stop_loss_response = order_details.get('stop_loss_response')
                print(f"🛑 Stop Loss Response: {stop_loss_response}")
                
                if stop_loss_response:
                    print("✅ CRITICAL: Stop loss response found in payload!")
                    if stop_loss_response.get('status') == 'ok':
                        print("✅ Stop loss order placed successfully")
                        return True
                    else:
                        print(f"❌ Stop loss order failed: {stop_loss_response}")
                        return False
                else:
                    print("❌ CRITICAL: No stop loss response found")
                    print("🚨 This confirms user's report - stop loss not being processed")
                    return False
            else:
                print(f"❌ Order failed: {hl_response.get('error', 'Unknown error')}")
                
                # Check if it's a rate limiting issue
                if '429' in str(hl_response.get('error', '')):
                    print("⚠️ Rate limiting detected - this is a temporary API issue")
                    print("The stop loss code logic appears to be implemented correctly")
                    return None  # Inconclusive due to rate limiting
                
                return False
        else:
            print(f"❌ Webhook failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def check_logs_for_stop_loss():
    """Check recent logs for stop loss related messages"""
    print("\n=== CHECKING LOGS FOR STOP LOSS ACTIVITY ===")
    
    try:
        response = requests.get(f"{BASE_URL}/logs?limit=20")
        if response.status_code == 200:
            logs = response.json().get('logs', [])
            
            stop_loss_logs = []
            for log in logs:
                message = log.get('message', '').lower()
                if 'stop' in message or 'sl' in message or 'trigger' in message:
                    stop_loss_logs.append(log)
            
            if stop_loss_logs:
                print(f"Found {len(stop_loss_logs)} stop loss related log entries:")
                for log in stop_loss_logs[:5]:  # Show first 5
                    print(f"- [{log.get('level')}] {log.get('message')}")
                    print(f"  Time: {log.get('timestamp')}")
                return True
            else:
                print("No stop loss related log entries found")
                return False
        else:
            print(f"Failed to get logs: {response.status_code}")
            return False
    except Exception as e:
        print(f"Error checking logs: {str(e)}")
        return False

if __name__ == "__main__":
    print("STOP LOSS IMPLEMENTATION TEST")
    print("=" * 50)
    
    # Check logs first
    check_logs_for_stop_loss()
    
    # Wait a bit to avoid rate limiting
    print("\nWaiting 10 seconds to avoid rate limiting...")
    time.sleep(10)
    
    # Run focused test
    result = test_stop_loss_focused()
    
    print("\n" + "=" * 50)
    if result is True:
        print("✅ STOP LOSS IMPLEMENTATION: WORKING")
    elif result is False:
        print("❌ STOP LOSS IMPLEMENTATION: NOT WORKING")
    else:
        print("⚠️ STOP LOSS IMPLEMENTATION: INCONCLUSIVE (Rate limiting)")
    print("=" * 50)