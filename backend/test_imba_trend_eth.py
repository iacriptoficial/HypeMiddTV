"""
Teste de webhook IMBA_TREND com ETH
Objetivo: Verificar se a formatação de preços inteiros funciona para ETH
"""

import requests
import json
import os
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '../frontend/.env')

BACKEND_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8001')

def test_imba_trend_eth():
    """Test IMBA_TREND strategy with ETH"""
    
    print("=" * 80)
    print("🧪 TEST: IMBA_TREND with ETH (Integer Price Formatting)")
    print("=" * 80)
    
    # Webhook payload for IMBA_TREND with ETH
    # ETH prices should be formatted as integers
    webhook_payload = {
        "strategy_id": "IMBA_TREND",
        "symbol": "ETH",
        "side": "buy",
        "entry": "market",
        "quantity": 0.01,  # Small quantity for testing
        "tp_price": 4650.75,  # Will be formatted to 4651.0 (integer)
        "sl_price": 4350.25   # Will be formatted to 4350.0 (integer)
    }
    
    print(f"\n📤 Sending webhook to {BACKEND_URL}/api/webhook/tradingview")
    print(f"Payload:")
    print(json.dumps(webhook_payload, indent=2))
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/webhook/tradingview",
            json=webhook_payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"\n📥 Response Status: {response.status_code}")
        print(f"Response:")
        print(json.dumps(response.json(), indent=2))
        
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "success":
                print(f"\n✅ TESTE PASSOU: Webhook processado com sucesso!")
                print(f"\nVerifique nos logs se:")
                print(f"  1. tp_price foi formatado de 4650.75 para 4651.0")
                print(f"  2. sl_price foi formatado de 4350.25 para 4350.0")
                print(f"  3. Nenhum erro 'Invalid TP/SL price. asset=4' apareceu")
                return True
            else:
                print(f"\n⚠️ TESTE FALHOU: Status não é 'success'")
                return False
        else:
            print(f"\n❌ TESTE FALHOU: Status code {response.status_code}")
            return False
            
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_imba_trend_sol():
    """Test IMBA_TREND strategy with SOL (decimal prices should work)"""
    
    print("\n" + "=" * 80)
    print("🧪 TEST: IMBA_TREND with SOL (Decimal Price Formatting)")
    print("=" * 80)
    
    webhook_payload = {
        "strategy_id": "IMBA_TREND",
        "symbol": "SOL",
        "side": "buy",
        "entry": "market",
        "quantity": 0.1,
        "tp_price": 235.45,  # Will stay as 235.45 (decimal OK for SOL)
        "sl_price": 220.78   # Will stay as 220.78 (decimal OK for SOL)
    }
    
    print(f"\n📤 Sending webhook to {BACKEND_URL}/api/webhook/tradingview")
    print(f"Payload:")
    print(json.dumps(webhook_payload, indent=2))
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/webhook/tradingview",
            json=webhook_payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"\n📥 Response Status: {response.status_code}")
        print(f"Response:")
        print(json.dumps(response.json(), indent=2))
        
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "success":
                print(f"\n✅ TESTE PASSOU: Webhook SOL processado com sucesso!")
                return True
            else:
                print(f"\n⚠️ TESTE FALHOU: Status não é 'success'")
                return False
        else:
            print(f"\n❌ TESTE FALHOU: Status code {response.status_code}")
            return False
            
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print(f"\n🚀 Testing IMBA_TREND Strategy with Asset-Specific Price Formatting")
    print(f"Backend URL: {BACKEND_URL}\n")
    
    # Test ETH (integer prices)
    eth_result = test_imba_trend_eth()
    
    # Wait a bit
    import time
    time.sleep(5)
    
    # Test SOL (decimal prices)
    sol_result = test_imba_trend_sol()
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print(f"ETH Test (integer formatting): {'✅ PASSED' if eth_result else '❌ FAILED'}")
    print(f"SOL Test (decimal formatting): {'✅ PASSED' if sol_result else '❌ FAILED'}")
    print("=" * 80)
    
    if eth_result and sol_result:
        print("\n✅ Todos os testes passaram! Implementação funcionando corretamente.")
    else:
        print("\n⚠️ Alguns testes falharam. Verifique os logs do backend.")
