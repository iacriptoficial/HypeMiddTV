"""
Script simplificado para testar TP/SL na Hyperliquid
Objetivo: Entender o comportamento atual antes de implementar ordens agrupadas
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
    # Simplificar - usar endereço da wallet direto
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

def test_sol_tpsl_with_decimals():
    """
    TESTE SOL: TP/SL com decimais (usuário disse que funciona)
    """
    print("\n" + "=" * 80)
    print("🧪 TESTE SOL: TP/SL com DECIMAIS")
    print("=" * 80)
    
    symbol = "SOL"
    
    # Get current price
    current_price = get_current_price(symbol)
    if not current_price:
        return False
    
    # Primeiro abrir uma posição pequena
    print(f"\n📤 Abrindo posição LONG de 0.1 SOL...")
    try:
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
            return False
            
        time.sleep(2)
        
        # Agora colocar TP/SL com decimais
        tp_price = round(current_price * 1.03, 2)  # +3% com decimais (e.g., 227.45)
        sl_price = round(current_price * 0.97, 2)  # -3% com decimais (e.g., 220.83)
        
        print(f"\n📤 Colocando TP com DECIMAL: ${tp_price}")
        tp_result = exchange.order(
            name=symbol,
            is_buy=False,
            sz=0.1,
            limit_px=tp_price,
            order_type={"trigger": {"triggerPx": tp_price, "isMarket": True, "tpsl": "tp"}},
            reduce_only=True
        )
        print(f"TP Result: {json.dumps(tp_result, indent=2)}")
        
        time.sleep(1)
        
        print(f"\n📤 Colocando SL com DECIMAL: ${sl_price}")
        sl_result = exchange.order(
            name=symbol,
            is_buy=False,
            sz=0.1,
            limit_px=sl_price,
            order_type={"trigger": {"triggerPx": sl_price, "isMarket": True, "tpsl": "sl"}},
            reduce_only=True
        )
        print(f"SL Result: {json.dumps(sl_result, indent=2)}")
        
        if tp_result and tp_result.get("status") == "ok" and sl_result and sl_result.get("status") == "ok":
            print(f"\n✅ SOL ACEITA DECIMAIS em TP/SL!")
            return True
        else:
            print(f"\n❌ SOL rejeitou ordens com decimais")
            return False
            
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_eth_tpsl_decimal_vs_integer():
    """
    TESTE ETH: Comparar DECIMAL vs INTEIRO
    """
    print("\n" + "=" * 80)
    print("🧪 TESTE ETH: TP/SL DECIMAL vs INTEIRO")
    print("=" * 80)
    
    symbol = "ETH"
    
    # Get current price
    current_price = get_current_price(symbol)
    if not current_price:
        return False
    
    # Primeiro abrir uma posição pequena
    print(f"\n📤 Abrindo posição LONG de 0.01 ETH...")
    try:
        entry_result = exchange.market_open(
            name=symbol,
            is_buy=True,
            sz=0.01,
            px=None,
            slippage=0.05
        )
        print(f"Resultado: {json.dumps(entry_result, indent=2)}")
        
        if not entry_result or entry_result.get("status") != "ok":
            print(f"❌ Falha ao abrir posição")
            return False
            
        time.sleep(2)
        
        # Teste A: TP com DECIMAL
        tp_price_decimal = round(current_price * 1.03, 2)  # +3% com decimais (e.g., 4464.19)
        
        print(f"\n📤 Teste A: TP com DECIMAL: ${tp_price_decimal}")
        try:
            tp_result = exchange.order(
                name=symbol,
                is_buy=False,
                sz=0.01,
                limit_px=tp_price_decimal,
                order_type={"trigger": {"triggerPx": tp_price_decimal, "isMarket": True, "tpsl": "tp"}},
                reduce_only=True
            )
            print(f"✅ TP DECIMAL ACEITO: {json.dumps(tp_result, indent=2)}")
            decimal_accepted = True
            
            # Cancelar ordem TP se foi aceita
            time.sleep(1)
            wallet_address = get_wallet_address()
            open_orders = info.open_orders(wallet_address)
            for order in open_orders:
                if order.get('coin') == symbol:
                    exchange.cancel(symbol, order.get('oid'))
                    print(f"  Ordem TP cancelada: {order.get('oid')}")
            
        except Exception as e:
            print(f"❌ TP DECIMAL REJEITADO: {e}")
            decimal_accepted = False
        
        time.sleep(2)
        
        # Teste B: TP com INTEIRO
        tp_price_int = int(current_price * 1.03)  # +3% inteiro (e.g., 4464.0)
        
        print(f"\n📤 Teste B: TP com INTEIRO: ${tp_price_int}.0")
        try:
            tp_result = exchange.order(
                name=symbol,
                is_buy=False,
                sz=0.01,
                limit_px=float(tp_price_int),
                order_type={"trigger": {"triggerPx": float(tp_price_int), "isMarket": True, "tpsl": "tp"}},
                reduce_only=True
            )
            print(f"✅ TP INTEIRO ACEITO: {json.dumps(tp_result, indent=2)}")
            integer_accepted = True
        except Exception as e:
            print(f"❌ TP INTEIRO REJEITADO: {e}")
            integer_accepted = False
        
        # Fechar posição e limpar
        print(f"\n🧹 Fechando posição...")
        try:
            close_result = exchange.market_close(name=symbol)
            print(f"Posição fechada: {json.dumps(close_result, indent=2)}")
        except:
            pass
        
        # Resultado
        print(f"\n📊 RESULTADO ETH:")
        print(f"  Decimal aceito: {'✅' if decimal_accepted else '❌'}")
        print(f"  Inteiro aceito: {'✅' if integer_accepted else '❌'}")
        
        if not decimal_accepted and integer_accepted:
            print(f"\n✅ CONFIRMADO: ETH rejeita decimais e aceita inteiros")
            return True
        elif decimal_accepted and integer_accepted:
            print(f"\n⚠️ ETH aceita AMBOS (decimal e inteiro)")
            return True
        else:
            print(f"\n❌ Resultado inesperado")
            return False
            
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n" + "=" * 80)
    print("🚀 TESTE SIMPLIFICADO - TP/SL BEHAVIOR")
    print("=" * 80)
    
    # Teste 1: SOL com decimais
    sol_result = test_sol_tpsl_with_decimals()
    time.sleep(3)
    
    # Teste 2: ETH decimal vs inteiro
    eth_result = test_eth_tpsl_decimal_vs_integer()
    
    print("\n" + "=" * 80)
    print("📊 RESUMO")
    print("=" * 80)
    print(f"  SOL com decimais: {'✅ PASSOU' if sol_result else '❌ FALHOU'}")
    print(f"  ETH decimal vs inteiro: {'✅ PASSOU' if eth_result else '❌ FALHOU'}")
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
