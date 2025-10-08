"""
TESTE CRÍTICO: Verificar ordens órfãs
Objetivo: Confirmar se TP/SL ficam órfãos ao fechar posição SEM grouping
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

environment = os.environ.get('ENVIRONMENT', 'testnet')
is_testnet = environment == 'testnet'
private_key = os.environ.get('HYPERLIQUID_TESTNET_KEY') if is_testnet else os.environ.get('HYPERLIQUID_MAINNET_KEY')
base_url = constants.TESTNET_API_URL if is_testnet else constants.MAINNET_API_URL

wallet = Account.from_key(private_key)
exchange = Exchange(wallet=wallet, base_url=base_url)
info = Info(base_url=base_url, skip_ws=True)

print(f"🔧 Environment: {environment}")
print(f"🔑 Wallet: {wallet.address}\n")

def get_open_orders(symbol: str):
    """Get open orders"""
    open_orders = info.open_orders(wallet.address)
    return [order for order in open_orders if order.get('coin') == symbol]

def main():
    symbol = "SOL"
    
    print("=" * 80)
    print("🧪 TESTE: Ordens Órfãs (Comportamento ATUAL sem grouping)")
    print("=" * 80)
    
    # Get price
    all_mids = info.all_mids()
    current_price = float(all_mids[symbol])
    print(f"📊 Preço atual {symbol}: ${current_price}\n")
    
    # Step 1: Open position
    print("📤 PASSO 1: Abrindo posição 0.1 SOL...")
    entry = exchange.market_open(name=symbol, is_buy=True, sz=0.1)
    print(f"✅ Posição aberta: {json.dumps(entry, indent=2)}\n")
    time.sleep(2)
    
    # Step 2: Place TP/SL WITHOUT grouping
    tp_price = round(current_price * 1.05, 2)
    sl_price = round(current_price * 0.95, 2)
    
    print(f"📤 PASSO 2: Colocando TP e SL (SEM grouping)")
    print(f"  TP: ${tp_price}")
    print(f"  SL: ${sl_price}\n")
    
    tp = exchange.order(
        name=symbol,
        is_buy=False,
        sz=0.1,
        limit_px=tp_price,
        order_type={"trigger": {"triggerPx": tp_price, "isMarket": True, "tpsl": "tp"}},
        reduce_only=True
    )
    print(f"TP: {json.dumps(tp, indent=2)}\n")
    time.sleep(1)
    
    sl = exchange.order(
        name=symbol,
        is_buy=False,
        sz=0.1,
        limit_px=sl_price,
        order_type={"trigger": {"triggerPx": sl_price, "isMarket": True, "tpsl": "sl"}},
        reduce_only=True
    )
    print(f"SL: {json.dumps(sl, indent=2)}\n")
    time.sleep(2)
    
    # Step 3: Check orders BEFORE closing
    orders_before = get_open_orders(symbol)
    print(f"📊 PASSO 3: Ordens ANTES de fechar posição: {len(orders_before)}")
    for order in orders_before:
        print(f"  - {order.get('side')} {order.get('sz')} @ ${order.get('limitPx')} (OID: {order.get('oid')})")
    print()
    
    # Step 4: Close position
    print("🔄 PASSO 4: Fechando posição manualmente...")
    close = exchange.market_close(coin=symbol)
    print(f"✅ Posição fechada: {json.dumps(close, indent=2)}\n")
    time.sleep(3)
    
    # Step 5: Check orders AFTER closing
    orders_after = get_open_orders(symbol)
    print(f"📊 PASSO 5: Ordens DEPOIS de fechar posição: {len(orders_after)}")
    for order in orders_after:
        print(f"  - {order.get('side')} {order.get('sz')} @ ${order.get('limitPx')} (OID: {order.get('oid')})")
    print()
    
    # Result
    print("=" * 80)
    print("📊 RESULTADO:")
    print("=" * 80)
    print(f"Ordens ANTES: {len(orders_before)}")
    print(f"Ordens DEPOIS: {len(orders_after)}")
    
    if len(orders_after) == 0:
        print("\n✅ SUCESSO: Hyperliquid já cancela TP/SL automaticamente!")
        print("   Não precisamos implementar cancelamento manual.")
    elif len(orders_after) > 0:
        print(f"\n❌ PROBLEMA CONFIRMADO: {len(orders_after)} ordens órfãs!")
        print("   Precisamos cancelar manualmente ou usar grouping.")
        
        # Clean up orphans
        print("\n🧹 Limpando ordens órfãs...")
        for order in orders_after:
            oid = order.get('oid')
            print(f"  Cancelando {oid}...")
            exchange.cancel(symbol, oid)
        print("✅ Ordens órfãs canceladas\n")
    
    print("=" * 80)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        import traceback
        traceback.print_exc()
