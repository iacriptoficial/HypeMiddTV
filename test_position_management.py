#!/usr/bin/env python3
"""
Test script to demonstrate position management functionality
"""

import requests
import json
import time

BASE_URL = "http://localhost:8001"

def send_webhook(symbol, side, quantity, price):
    """Send webhook to the API"""
    payload = {
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "entry": "market",
        "price": price
    }
    
    response = requests.post(f"{BASE_URL}/api/webhook/tradingview", json=payload)
    return response.json()

def test_position_management():
    """Test position management functionality"""
    print("=== TESTE DE GERENCIAMENTO DE POSIÇÕES ===")
    
    # Test 1: Create initial position
    print("\n1. Criando posição inicial...")
    result1 = send_webhook("SOL", "buy", 0.1, 160)
    print(f"Status: {result1.get('status')}")
    
    if result1.get('status') == 'success':
        hl_response = result1.get('hyperliquid_response', {})
        print(f"Hyperliquid Status: {hl_response.get('status')}")
        print(f"Message: {hl_response.get('message')}")
    
    # Wait a bit
    time.sleep(5)
    
    # Test 2: Send opposite signal (should close existing position first)
    print("\n2. Enviando sinal oposto (deve fechar posição existente)...")
    result2 = send_webhook("SOL", "sell", 0.05, 155)
    print(f"Status: {result2.get('status')}")
    
    if result2.get('status') == 'success':
        hl_response = result2.get('hyperliquid_response', {})
        print(f"Hyperliquid Status: {hl_response.get('status')}")
        print(f"Message: {hl_response.get('message')}")
    
    # Check logs for position management
    print("\n3. Verificando logs de gerenciamento de posições...")
    logs_response = requests.get(f"{BASE_URL}/api/logs?limit=20")
    if logs_response.status_code == 200:
        logs = logs_response.json().get('logs', [])
        
        print("Logs relevantes:")
        for log in logs:
            message = log.get('message', '')
            if any(keyword in message for keyword in ['position', 'Position', 'close', 'Close', 'Found', 'Successfully']):
                print(f"  - {log.get('level')}: {message}")

if __name__ == "__main__":
    test_position_management()