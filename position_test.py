#!/usr/bin/env python3
import requests
import json
from datetime import datetime

# Base URL from frontend/.env
BASE_URL = "https://strat-manager.preview.emergentagent.com/api"

def test_position_clearing_detailed():
    """Detailed test of position clearing mechanism"""
    print("=== DETAILED POSITION CLEARING TEST ===")
    print("🎯 Testing the exact scenario: -10.73 SOL position clearing")
    
    # First, let's try to place a small order to create a position
    print("\n--- Step 1: Creating a small position for testing ---")
    create_position_payload = {
        "symbol": "SOL",
        "side": "sell",  # Create short position
        "entry": "market",
        "quantity": "0.1",  # Small amount for testing
        "price": "175.00"
    }
    
    url = f"{BASE_URL}/webhook/tradingview"
    
    try:
        response = requests.post(url, json=create_position_payload)
        print(f"Create position response: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Position creation result: {json.dumps(result, indent=2)}")
        else:
            print(f"Failed to create position: {response.text}")
    except Exception as e:
        print(f"Error creating position: {str(e)}")
    
    print("\n--- Step 2: Testing position clearing with opposite order ---")
    # Now try to place opposite order that should trigger position clearing
    clear_position_payload = {
        "symbol": "SOL",
        "side": "buy",  # Opposite side to trigger clearing
        "entry": "market", 
        "quantity": "0.2",  # Larger than existing position
        "price": "175.00"
    }
    
    try:
        response = requests.post(url, json=clear_position_payload)
        print(f"Position clearing test response: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Position clearing result: {json.dumps(result, indent=2)}")
            
            # Check for specific errors
            response_str = str(result).lower()
            if 'market_close' in response_str:
                print("✅ market_close method is being used")
            else:
                print("❌ market_close method not detected")
                
            if 'order could not immediately match' in response_str:
                print("❌ CRITICAL: 'Order could not immediately match' error still present!")
            else:
                print("✅ No 'Order could not immediately match' error")
                
            if 'failed to clear' in response_str:
                print("❌ Position clearing is failing")
            else:
                print("✅ Position clearing appears successful")
                
        else:
            print(f"Failed position clearing test: {response.text}")
    except Exception as e:
        print(f"Error in position clearing test: {str(e)}")
    
    print("\n--- Step 3: Checking recent logs for detailed error info ---")
    try:
        logs_response = requests.get(f"{BASE_URL}/logs")
        if logs_response.status_code == 200:
            logs_data = logs_response.json()
            recent_logs = logs_data.get('logs', [])[:20]
            
            print("Recent logs related to position clearing:")
            for log in recent_logs:
                message = log.get('message', '')
                level = log.get('level', '')
                timestamp = log.get('timestamp', '')
                
                if any(keyword in message.lower() for keyword in ['position', 'close', 'market_close', 'clear', 'error']):
                    print(f"[{level}] {timestamp}: {message}")
        else:
            print(f"Failed to get logs: {logs_response.status_code}")
    except Exception as e:
        print(f"Error getting logs: {str(e)}")

if __name__ == "__main__":
    test_position_clearing_detailed()