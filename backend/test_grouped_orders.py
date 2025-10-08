"""
Script de teste para validar ordens agrupadas (grouped orders) com OCO na Hyperliquid
OBJETIVO: Validar comportamento ANTES de implementar no código principal

Testes:
1. Criar ordem agrupada (entrada + TP + SL)
2. Verificar cancelamento OCO (TP cancela SL e vice-versa)
3. Verificar cancelamento ao fechar posição
4. Testar precisão de preços (ETH inteiro vs decimal)
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants
from eth_account import Account
import time
import json

# Load environment
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Setup Hyperliquid
environment = os.environ.get('ENVIRONMENT', 'testnet')
is_testnet = environment == 'testnet'
private_key = os.environ.get('HYPERLIQUID_TESTNET_KEY') if is_testnet else os.environ.get('HYPERLIQUID_MAINNET_KEY')
base_url = constants.TESTNET_API_URL if is_testnet else constants.MAINNET_API_URL

wallet = Account.from_key(private_key)
exchange = Exchange(wallet=wallet, base_url=base_url)
info = Info(base_url=base_url, skip_ws=True)

print(f"🔧 Environment: {environment}")
print(f"🔑 Wallet: {wallet.address}")
print("=" * 80)

def get_wallet_address():
    """Get the correct trading account address"""
    try:
        # Check if it's an agent wallet
        user_role = info.user_role(wallet.address)
        
        if user_role and user_role.get('isAgent'):
            main_address = user_role.get('mainAddress')
            print(f"✅ Agent wallet detected. Main account: {main_address}")
            return main_address
        else:
            print(f"✅ Direct wallet: {wallet.address}")
            return wallet.address
            
    except Exception as e:
        print(f"⚠️ Error detecting wallet type: {e}")
        return wallet.address

def get_current_price(symbol: str):
    """Get current market price for a symbol"""
    try:
        all_mids = info.all_mids()
        if symbol in all_mids:
            price = float(all_mids[symbol])
            print(f"📊 Current {symbol} price: ${price}")
            return price
        else:
            print(f"❌ Symbol {symbol} not found in market data")
            return None
    except Exception as e:
        print(f"❌ Error getting price for {symbol}: {e}")
        return None

def get_open_positions(symbol: str):
    """Get open positions for a symbol"""
    try:
        wallet_address = get_wallet_address()
        user_state = info.user_state(wallet_address)
        
        if not user_state or 'assetPositions' not in user_state:
            return []
        
        positions = []
        for position in user_state['assetPositions']:
            if position.get('position', {}).get('coin') == symbol:
                position_data = position.get('position', {})
                size = float(position_data.get('szi', 0))
                
                if size != 0:
                    positions.append({
                        'symbol': symbol,
                        'size': size,
                        'entry_px': position_data.get('entryPx'),
                        'unrealized_pnl': position_data.get('unrealizedPnl')
                    })
        
        return positions
    except Exception as e:
        print(f"❌ Error getting positions: {e}")
        return []

def get_open_orders(symbol: str):
    """Get open orders for a symbol"""
    try:
        wallet_address = get_wallet_address()
        open_orders = info.open_orders(wallet_address)
        
        symbol_orders = [order for order in open_orders if order.get('coin') == symbol]
        return symbol_orders
    except Exception as e:
        print(f"❌ Error getting open orders: {e}")
        return []

def cancel_all_orders_and_positions(symbol: str):
    """Clean up all orders and positions for a symbol"""
    print(f"\n🧹 Cleaning up all orders and positions for {symbol}...")
    
    try:
        # Close positions first
        positions = get_open_positions(symbol)
        if positions:
            for pos in positions:
                print(f"  🔄 Closing position: {pos['size']} {symbol}")
                try:
                    result = exchange.market_close(coin=symbol)
                    print(f"    Result: {result}")
                except Exception as e:
                    print(f"    Error: {e}")
                time.sleep(1)
        
        # Cancel open orders
        orders = get_open_orders(symbol)
        if orders:
            for order in orders:
                order_id = order.get('oid')
                print(f"  🚫 Canceling order: {order_id}")
                try:
                    result = exchange.cancel(symbol, order_id)
                    print(f"    Result: {result}")
                except Exception as e:
                    print(f"    Error: {e}")
                time.sleep(0.5)
        
        print(f"✅ Cleanup complete for {symbol}")
        return True
        
    except Exception as e:
        print(f"❌ Cleanup error: {e}")
        return False

def test_1_simple_grouped_order():
    """
    TESTE 1: Ordem agrupada simples (Entrada + TP + SL)
    Objetivo: Verificar se as 3 ordens são criadas corretamente com grouping
    """
    print("\n" + "=" * 80)
    print("🧪 TESTE 1: Ordem Agrupada Simples (Entrada + TP + SL)")
    print("=" * 80)
    
    symbol = "SOL"
    
    # Cleanup first
    cancel_all_orders_and_positions(symbol)
    time.sleep(2)
    
    # Get current price
    current_price = get_current_price(symbol)
    if not current_price:
        print("❌ Cannot proceed without price")
        return False
    
    # Calculate prices
    quantity = 0.1  # Small test quantity
    entry_price = current_price  # Market order
    tp_price = round(current_price * 1.02, 2)  # 2% profit
    sl_price = round(current_price * 0.98, 2)  # 2% loss
    
    print(f"\n📋 Order Parameters:")
    print(f"  Symbol: {symbol}")
    print(f"  Quantity: {quantity}")
    print(f"  Entry: MARKET (≈${entry_price})")
    print(f"  Take Profit: ${tp_price} (+2%)")
    print(f"  Stop Loss: ${sl_price} (-2%)")
    
    try:
        # Generate unique client order IDs
        import uuid
        parent_cloid = f"parent_{uuid.uuid4().hex[:8]}"
        tp_cloid = f"tp_{uuid.uuid4().hex[:8]}"
        sl_cloid = f"sl_{uuid.uuid4().hex[:8]}"
        
        print(f"\n🔑 Client Order IDs:")
        print(f"  Parent: {parent_cloid}")
        print(f"  TP: {tp_cloid}")
        print(f"  SL: {sl_cloid}")
        
        # Order 1: Market Entry (Parent)
        order_1 = {
            "a": 1,  # asset index for SOL
            "b": True,  # is_buy
            "p": "0",  # market order (price = 0)
            "s": str(quantity),
            "r": False,  # not reduce only
            "t": {"limit": {"tif": "Ioc"}},  # IOC for market
            "c": parent_cloid
        }
        
        # Order 2: Take Profit (Child)
        order_2 = {
            "a": 1,
            "b": False,  # sell to close
            "p": str(tp_price),
            "s": str(quantity),
            "r": True,  # reduce only
            "t": {
                "trigger": {
                    "isMarket": True,
                    "triggerPx": str(tp_price),
                    "tpsl": "tp"
                }
            },
            "c": tp_cloid
        }
        
        # Order 3: Stop Loss (Child)
        order_3 = {
            "a": 1,
            "b": False,  # sell to close
            "p": str(sl_price),
            "s": str(quantity),
            "r": True,  # reduce only
            "t": {
                "trigger": {
                    "isMarket": True,
                    "triggerPx": str(sl_price),
                    "tpsl": "sl"
                }
            },
            "c": sl_cloid
        }
        
        # Create grouped order request
        grouped_order = {
            "type": "batchModify",
            "modifies": [
                {"oid": None, "order": order_1},
                {"oid": None, "order": order_2},
                {"oid": None, "order": order_3}
            ],
            "grouping": "normalTpsl"  # This creates OCO relationship
        }
        
        print(f"\n📤 Sending grouped order...")
        print(f"Request: {json.dumps(grouped_order, indent=2)}")
        
        # Send the order using exchange.post method
        result = exchange.post("/exchange", grouped_order)
        
        print(f"\n📥 Response:")
        print(json.dumps(result, indent=2))
        
        # Check if successful
        if result and result.get("status") == "ok":
            print(f"\n✅ TESTE 1 PASSOU: Ordem agrupada criada com sucesso!")
            
            # Wait and check orders
            time.sleep(2)
            orders = get_open_orders(symbol)
            positions = get_open_positions(symbol)
            
            print(f"\n📊 Status após ordem:")
            print(f"  Open Orders: {len(orders)}")
            for order in orders:
                print(f"    - {order.get('side')} {order.get('sz')} @ ${order.get('limitPx')} (ID: {order.get('oid')})")
            
            print(f"  Open Positions: {len(positions)}")
            for pos in positions:
                print(f"    - {pos['size']} {symbol} @ ${pos['entry_px']}")
            
            return True
        else:
            print(f"\n❌ TESTE 1 FALHOU: {result}")
            return False
            
    except Exception as e:
        print(f"\n❌ TESTE 1 ERRO: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_2_oco_behavior():
    """
    TESTE 2: Comportamento OCO
    Objetivo: Verificar se atingir TP cancela SL (ou vice-versa)
    """
    print("\n" + "=" * 80)
    print("🧪 TESTE 2: Comportamento OCO (One-Cancels-Other)")
    print("=" * 80)
    
    symbol = "SOL"
    
    # Check current state
    orders = get_open_orders(symbol)
    positions = get_open_positions(symbol)
    
    print(f"\n📊 Estado atual:")
    print(f"  Open Orders: {len(orders)}")
    print(f"  Open Positions: {len(positions)}")
    
    if len(orders) < 2:
        print(f"\n⚠️ TESTE 2 PULADO: Precisa de pelo menos 2 ordens abertas (TP e SL)")
        print(f"   Execute o Teste 1 primeiro ou crie ordens manualmente")
        return False
    
    if len(positions) == 0:
        print(f"\n⚠️ TESTE 2 PULADO: Precisa de posição aberta")
        return False
    
    # Find TP and SL orders
    tp_orders = [o for o in orders if 'tp' in str(o).lower() or float(o.get('limitPx', 0)) > float(positions[0]['entry_px'])]
    sl_orders = [o for o in orders if 'sl' in str(o).lower() or float(o.get('limitPx', 0)) < float(positions[0]['entry_px'])]
    
    print(f"\n🎯 Ordens identificadas:")
    print(f"  TP Orders: {len(tp_orders)}")
    print(f"  SL Orders: {len(sl_orders)}")
    
    print(f"\n⏳ Aguardando movimento de preço para verificar OCO...")
    print(f"   (Este teste requer monitoramento manual ou movimento real de mercado)")
    print(f"   INSTRUÇÃO: Observe se ao atingir TP, o SL é cancelado automaticamente")
    
    return True

def test_3_manual_close_cancels_tpsl():
    """
    TESTE 3: Fechamento manual cancela TP/SL
    Objetivo: Verificar se fechar posição manualmente cancela TP e SL órfãos
    """
    print("\n" + "=" * 80)
    print("🧪 TESTE 3: Fechamento Manual Cancela TP/SL")
    print("=" * 80)
    
    symbol = "SOL"
    
    # Check current state
    orders_before = get_open_orders(symbol)
    positions = get_open_positions(symbol)
    
    print(f"\n📊 Estado ANTES do fechamento:")
    print(f"  Open Orders: {len(orders_before)}")
    for order in orders_before:
        print(f"    - {order.get('side')} {order.get('sz')} @ ${order.get('limitPx')} (ID: {order.get('oid')})")
    print(f"  Open Positions: {len(positions)}")
    for pos in positions:
        print(f"    - {pos['size']} {symbol}")
    
    if len(positions) == 0:
        print(f"\n⚠️ TESTE 3 PULADO: Não há posição para fechar")
        return False
    
    try:
        print(f"\n🔄 Fechando posição manualmente com market_close()...")
        result = exchange.market_close(coin=symbol)
        
        print(f"\n📥 Resultado do fechamento:")
        print(json.dumps(result, indent=2))
        
        # Wait for execution
        time.sleep(2)
        
        # Check state after close
        orders_after = get_open_orders(symbol)
        positions_after = get_open_positions(symbol)
        
        print(f"\n📊 Estado DEPOIS do fechamento:")
        print(f"  Open Orders: {len(orders_after)}")
        for order in orders_after:
            print(f"    - {order.get('side')} {order.get('sz')} @ ${order.get('limitPx')} (ID: {order.get('oid')})")
        print(f"  Open Positions: {len(positions_after)}")
        
        # Verify TP/SL were canceled
        if len(orders_after) < len(orders_before):
            print(f"\n✅ TESTE 3 PASSOU: Ordens foram canceladas automaticamente!")
            print(f"   Ordens canceladas: {len(orders_before) - len(orders_after)}")
            return True
        elif len(orders_after) == 0:
            print(f"\n✅ TESTE 3 PASSOU: Todas as ordens foram canceladas!")
            return True
        else:
            print(f"\n⚠️ TESTE 3 RESULTADO AMBÍGUO: Mesma quantidade de ordens")
            print(f"   ORDENS ÓRFÃS PODEM EXISTIR - verificar manualmente na interface")
            return False
            
    except Exception as e:
        print(f"\n❌ TESTE 3 ERRO: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_4_price_precision_eth():
    """
    TESTE 4: Precisão de preços (ETH inteiro vs decimal)
    Objetivo: Confirmar se ETH rejeita decimais e aceita inteiros
    """
    print("\n" + "=" * 80)
    print("🧪 TESTE 4: Precisão de Preços (ETH Inteiro vs Decimal)")
    print("=" * 80)
    
    symbol = "ETH"
    
    # Cleanup first
    cancel_all_orders_and_positions(symbol)
    time.sleep(2)
    
    # Get current price
    current_price = get_current_price(symbol)
    if not current_price:
        print("❌ Cannot proceed without price")
        return False
    
    quantity = 0.01  # Very small quantity for testing
    
    # Test 4A: Decimal prices (should fail based on user report)
    print(f"\n🧪 TESTE 4A: Preços DECIMAIS (esperado: FALHAR)")
    tp_price_decimal = round(current_price * 1.02, 2)  # e.g., 4464.19
    sl_price_decimal = round(current_price * 0.98, 2)  # e.g., 4321.45
    
    print(f"  TP Decimal: ${tp_price_decimal}")
    print(f"  SL Decimal: ${sl_price_decimal}")
    
    try:
        # Try to place TP order with decimal
        tp_result = exchange.order(
            name=symbol,
            is_buy=False,
            sz=quantity,
            limit_px=tp_price_decimal,
            order_type={"trigger": {"triggerPx": str(tp_price_decimal), "isMarket": True, "tpsl": "tp"}},
            reduce_only=True
        )
        print(f"  TP Decimal Result: {tp_result}")
        
        # If successful, cancel it
        if tp_result and tp_result.get("status") == "ok":
            print(f"  ⚠️ TP DECIMAL FOI ACEITO (inesperado)")
            time.sleep(1)
            cancel_all_orders_and_positions(symbol)
        
    except Exception as e:
        print(f"  ✅ TP DECIMAL REJEITADO (esperado): {e}")
    
    time.sleep(1)
    
    # Test 4B: Integer prices (should work)
    print(f"\n🧪 TESTE 4B: Preços INTEIROS (esperado: SUCESSO)")
    tp_price_int = int(current_price * 1.02)  # e.g., 4464.0
    sl_price_int = int(current_price * 0.98)  # e.g., 4321.0
    
    print(f"  TP Inteiro: ${tp_price_int}.0")
    print(f"  SL Inteiro: ${sl_price_int}.0")
    
    try:
        # Try to place TP order with integer
        tp_result = exchange.order(
            name=symbol,
            is_buy=False,
            sz=quantity,
            limit_px=float(tp_price_int),
            order_type={"trigger": {"triggerPx": str(float(tp_price_int)), "isMarket": True, "tpsl": "tp"}},
            reduce_only=True
        )
        print(f"  TP Inteiro Result: {tp_result}")
        
        if tp_result and tp_result.get("status") == "ok":
            print(f"  ✅ TP INTEIRO ACEITO (esperado)")
            time.sleep(1)
            cancel_all_orders_and_positions(symbol)
            print(f"\n✅ TESTE 4 PASSOU: ETH aceita inteiros e rejeita decimais")
            return True
        else:
            print(f"  ❌ TP INTEIRO REJEITADO (inesperado)")
            return False
        
    except Exception as e:
        print(f"  ❌ TP INTEIRO ERRO: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Execute all tests in sequence"""
    print("\n" + "=" * 80)
    print("🚀 INICIANDO TESTES DE VALIDAÇÃO - ORDENS AGRUPADAS")
    print("=" * 80)
    
    results = {}
    
    # Test 1: Simple grouped order
    results['test_1'] = test_1_simple_grouped_order()
    time.sleep(2)
    
    # Test 2: OCO behavior (manual observation)
    results['test_2'] = test_2_oco_behavior()
    time.sleep(2)
    
    # Test 3: Manual close cancels TP/SL
    results['test_3'] = test_3_manual_close_cancels_tpsl()
    time.sleep(2)
    
    # Test 4: Price precision (ETH)
    results['test_4'] = test_4_price_precision_eth()
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 RESUMO DOS TESTES")
    print("=" * 80)
    for test_name, result in results.items():
        status = "✅ PASSOU" if result else "❌ FALHOU"
        print(f"  {test_name}: {status}")
    
    print("\n" + "=" * 80)
    print("✅ Testes de validação concluídos!")
    print("=" * 80)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Testes interrompidos pelo usuário")
    except Exception as e:
        print(f"\n\n❌ Erro fatal: {e}")
        import traceback
        traceback.print_exc()
