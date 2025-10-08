#!/usr/bin/env python3
import requests
import json
import time
from datetime import datetime

# Base URL from frontend/.env
BASE_URL = "https://strat-manager.preview.emergentagent.com/api"

def test_comprehensive_stop_loss():
    """Comprehensive test of stop loss functionality"""
    print("=== COMPREHENSIVE STOP LOSS TESTS ===")
    print("🎯 Testing all stop loss scenarios as requested in review")
    
    tests = [
        {
            "name": "SOL BUY with Stop Loss",
            "payload": {
                "symbol": "SOL",
                "side": "buy",
                "entry": "market",
                "quantity": "0.1",
                "price": "160.00",
                "stop": "158.00"
            }
        },
        {
            "name": "BTC SELL with Stop Loss",
            "payload": {
                "symbol": "BTC",
                "side": "sell",
                "entry": "market",
                "quantity": "0.01",
                "price": "45000.00",
                "stop": "46000.00"
            }
        },
        {
            "name": "ETH LIMIT BUY with Stop Loss",
            "payload": {
                "symbol": "ETH",
                "side": "buy",
                "entry": "limit",
                "quantity": "0.01",
                "price": "3200.00",
                "stop": "3150.00"
            }
        }
    ]
    
    results = []
    url = f"{BASE_URL}/webhook/tradingview"
    
    for i, test in enumerate(tests):
        print(f"\n--- Test {i+1}: {test['name']} ---")
        
        try:
            response = requests.post(url, json=test['payload'])
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                hl_response = result.get('hyperliquid_response', {})
                
                if hl_response.get('status') == 'success':
                    order_details = hl_response.get('order_details', {})
                    main_order = order_details.get('hyperliquid_response')
                    stop_loss_response = order_details.get('stop_loss_response')
                    
                    # Check main order
                    main_success = main_order and main_order.get('status') == 'ok'
                    main_oid = None
                    if main_success:
                        statuses = main_order.get('response', {}).get('data', {}).get('statuses', [])
                        for status in statuses:
                            if 'filled' in status:
                                main_oid = status['filled'].get('oid')
                            elif 'resting' in status:
                                main_oid = status['resting'].get('oid')
                    
                    # Check stop loss
                    stop_success = stop_loss_response and stop_loss_response.get('status') == 'ok'
                    stop_oid = None
                    if stop_success:
                        statuses = stop_loss_response.get('response', {}).get('data', {}).get('statuses', [])
                        for status in statuses:
                            if 'resting' in status:
                                stop_oid = status['resting'].get('oid')
                    
                    print(f"✅ Main Order: {'SUCCESS' if main_success else 'FAILED'} (ID: {main_oid})")
                    print(f"✅ Stop Loss: {'SUCCESS' if stop_success else 'FAILED'} (ID: {stop_oid})")
                    
                    results.append({
                        'test': test['name'],
                        'main_order': main_success,
                        'stop_loss': stop_success,
                        'main_oid': main_oid,
                        'stop_oid': stop_oid
                    })
                    
                else:
                    print(f"❌ Order failed: {hl_response.get('message')}")
                    results.append({
                        'test': test['name'],
                        'main_order': False,
                        'stop_loss': False,
                        'error': hl_response.get('message')
                    })
            else:
                print(f"❌ Webhook failed: {response.status_code}")
                results.append({
                    'test': test['name'],
                    'main_order': False,
                    'stop_loss': False,
                    'error': f"HTTP {response.status_code}"
                })
                
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            results.append({
                'test': test['name'],
                'main_order': False,
                'stop_loss': False,
                'error': str(e)
            })
        
        # Wait between tests to avoid rate limiting
        if i < len(tests) - 1:
            print("Waiting 15 seconds to avoid rate limiting...")
            time.sleep(15)
    
    # Summary
    print("\n" + "=" * 60)
    print("COMPREHENSIVE STOP LOSS TEST RESULTS")
    print("=" * 60)
    
    all_passed = True
    for result in results:
        main_status = "✅" if result.get('main_order') else "❌"
        stop_status = "✅" if result.get('stop_loss') else "❌"
        
        print(f"{result['test']}:")
        print(f"  Main Order: {main_status} {result.get('main_oid', '')}")
        print(f"  Stop Loss:  {stop_status} {result.get('stop_oid', '')}")
        
        if 'error' in result:
            print(f"  Error: {result['error']}")
        
        if not (result.get('main_order') and result.get('stop_loss')):
            all_passed = False
        
        print()
    
    print("=" * 60)
    if all_passed:
        print("✅ ALL STOP LOSS TESTS PASSED!")
        print("🎯 CRITICAL SUCCESS: Stop loss functionality is fully working!")
    else:
        print("❌ SOME STOP LOSS TESTS FAILED")
    print("=" * 60)
    
    return all_passed

if __name__ == "__main__":
    test_comprehensive_stop_loss()