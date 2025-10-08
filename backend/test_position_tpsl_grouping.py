"""
TESTE CRÍTICO: Ordens agrupadas Position TP/SL
Objetivo: Verificar se ao atingir TP, o SL é cancelado automaticamente (OCO)
"""

import os
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

def get_current_price(symbol: str):
    """Get current market price"""
    all_mids = info.all_mids()
    if symbol in all_mids:
        price = float(all_mids[symbol])
        print(f"📊 Current {symbol} price: ${price}")
        return price
    return None

def get_open_orders(symbol: str):
    """Get open orders"""
    try:
        open_orders = info.open_orders(wallet.address)
        symbol_orders = [order for order in open_orders if order.get('coin') == symbol]
        return symbol_orders
    except Exception as e:
        print(f"❌ Error getting orders: {e}")
        return []

def main():
    print("\n" + "=" * 80)
    print("🧪 TESTE: Position TP/SL com Grouping (OCO)")
    print("=" * 80)
    
    symbol = "SOL"
    
    # Get current price
    current_price = get_current_price(symbol)
    if not current_price:
        print("❌ Cannot get price")
        return
    
    # Step 1: Open a position
    print(f"\n📤 PASSO 1: Abrindo posição LONG de 0.1 SOL...")
    entry_result = exchange.market_open(
        name=symbol,
        is_buy=True,
        sz=0.1,
        px=None,
        slippage=0.05
    )
    print(f"Resultado: {json.dumps(entry_result, indent=2)}")
    
    if not entry_result or entry_result.get("status") != "ok":
        print(f"❌ Falha ao abrir posição")
        return
    
    time.sleep(2)
    
    # Step 2: Place TP and SL as grouped position orders
    tp_price = round(current_price * 1.05, 2)  # +5%
    sl_price = round(current_price * 0.95, 2)  # -5%
    
    print(f"\n📤 PASSO 2: Colocando TP/SL AGRUPADOS")
    print(f"  TP: ${tp_price} (+5%)")
    print(f"  SL: ${sl_price} (-5%)")
    
    # Method 1: Try usando bulk_orders com cloid agrupado
    print(f"\n🔧 Tentativa 1: Usando bulk_orders com cloid agrupado...")
    try:
        import uuid
        group_id = f"group_{uuid.uuid4().hex[:8]}"
        
        tp_result = exchange.order(
            name=symbol,
            is_buy=False,
            sz=0.1,
            limit_px=tp_price,
            order_type={"trigger": {"triggerPx": tp_price, "isMarket": True, "tpsl": "tp"}},
            reduce_only=True,
            cloid=f"{group_id}_tp"
        )
        print(f"TP Result: {json.dumps(tp_result, indent=2)}")
        
        time.sleep(1)
        
        sl_result = exchange.order(
            name=symbol,
            is_buy=False,
            sz=0.1,
            limit_px=sl_price,
            order_type={"trigger": {"triggerPx": sl_price, "isMarket": True, "tpsl": "sl"}},
            reduce_only=True,
            cloid=f"{group_id}_sl"
        )
        print(f"SL Result: {json.dumps(sl_result, indent=2)}")
        
    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
    
    time.sleep(2)
    
    # Step 3: Check orders
    orders = get_open_orders(symbol)
    print(f"\n📊 PASSO 3: Ordens abertas: {len(orders)}")
    for order in orders:
        print(f"  - {order.get('side')} {order.get('sz')} @ ${order.get('limitPx')} (ID: {order.get('oid')})")
    
    if len(orders) < 2:
        print(f"\n⚠️ Menos de 2 ordens abertas - agrupamento pode não estar funcionando")
    
    # Step 4: Instructions for manual testing
    print(f"\n" + "=" * 80)
    print(f"📝 PRÓXIMOS PASSOS PARA TESTE MANUAL:")
    print(f"=" * 80)
    print(f"1. Acesse a interface da Hyperliquid Testnet")
    print(f"2. Verifique se as ordens TP e SL estão visíveis")
    print(f"3. Aguarde o preço atingir TP ou SL")
    print(f"4. Observe se a outra ordem é cancelada automaticamente")
    print(f"\n   OU")
    print(f"\n5. Feche a posição manualmente")
    print(f"6. Verifique se TP e SL são cancelados")
    print(f"\n⏳ Aguardando 30 segundos antes de limpar...")
    
    # Wait a bit
    time.sleep(30)
    
    # Step 5: Clean up
    print(f"\n🧹 PASSO 5: Limpando posições e ordens...")
    try:
        close_result = exchange.market_close(name=symbol)
        print(f"Posição fechada: {json.dumps(close_result, indent=2)}")
        
        time.sleep(2)
        
        # Check if orders were canceled
        orders_after = get_open_orders(symbol)
        print(f"\n📊 Ordens após fechar posição: {len(orders_after)}")
        
        if len(orders_after) == 0:
            print(f"✅ SUCESSO: Todas as ordens foram canceladas ao fechar a posição!")
        elif len(orders_after) < len(orders):
            print(f"⚠️ PARCIAL: Algumas ordens foram canceladas ({len(orders)} -> {len(orders_after)})")
        else:
            print(f"❌ FALHA: Ordens não foram canceladas (ainda {len(orders_after)} órfãs)")
            
            # Cancel manually
            for order in orders_after:
                order_id = order.get('oid')
                print(f"  Cancelando manualmente: {order_id}")
                exchange.cancel(symbol, order_id)
        
    except Exception as e:
        print(f"❌ Erro ao limpar: {e}")
    
    print(f"\n" + "=" * 80)
    print(f"✅ Teste concluído")
    print(f"=" * 80)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Teste interrompido")
    except Exception as e:
        print(f"\n\n❌ Erro fatal: {e}")
        import traceback
        traceback.print_exc()
