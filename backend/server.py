from fastapi import FastAPI, APIRouter, HTTPException, Request
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime
import pytz
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants
import json
import asyncio
from collections import defaultdict

# Configure Brazilian timezone
BRAZIL_TZ = pytz.timezone('America/Sao_Paulo')

def get_brazil_time():
    """Get current time in Brazilian timezone (GMT-3)"""
    return datetime.now(BRAZIL_TZ)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI(title="TradingView to Hyperliquid Middleware")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Custom formatter for Brazilian timezone
class BrazilTimeFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        ct = get_brazil_time()
        if datefmt:
            return ct.strftime(datefmt)
        else:
            return ct.strftime('%Y-%m-%d %H:%M:%S %Z')

# Configure logging with Brazilian timezone
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Apply custom formatter to all handlers
for handler in logging.getLogger().handlers:
    handler.setFormatter(BrazilTimeFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger = logging.getLogger(__name__)

# Hyperliquid Configuration
class HyperliquidConfig:
    def __init__(self):
        self.environment = os.environ.get('ENVIRONMENT', 'testnet')
        self.is_testnet = self.environment == 'testnet'
        self.private_key = (
            os.environ.get('HYPERLIQUID_TESTNET_KEY') if self.is_testnet 
            else os.environ.get('HYPERLIQUID_MAINNET_KEY')
        )
        self.base_url = constants.TESTNET_API_URL if self.is_testnet else constants.MAINNET_API_URL
        
    def get_info_client(self):
        return Info(base_url=self.base_url, skip_ws=True)
    
    def get_exchange_client(self):
        if not self.private_key:
            raise ValueError(f"No private key configured for {self.environment}")
        
        from eth_account import Account
        wallet = Account.from_key(self.private_key)
        
        return Exchange(
            wallet=wallet,
            base_url=self.base_url
        )

# Global config instance
hyperliquid_config = HyperliquidConfig()

# Data Models
class WebhookMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: get_brazil_time().isoformat())
    source: str = "tradingview"
    payload: Dict[str, Any]
    status: str = "received"
    error: Optional[str] = None

class HyperliquidResponse(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: get_brazil_time().isoformat())
    webhook_id: str
    response_data: Dict[str, Any]
    status: str = "sent"
    error: Optional[str] = None

class ServerStatus(BaseModel):
    status: str
    environment: str
    timestamp: str
    uptime: str
    total_webhooks: int
    successful_forwards: int
    failed_forwards: int
    hyperliquid_connected: bool
    balance: Optional[float] = None
    wallet_address: Optional[str] = None
    
class LogEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: get_brazil_time().isoformat())
    level: str
    message: str
    details: Optional[Dict[str, Any]] = None

# Global stats
stats = defaultdict(int)
server_start_time = get_brazil_time()

# Utility functions
async def log_message(level: str, message: str, details: Optional[Dict[str, Any]] = None):
    """Log message to database and console"""
    log_entry = LogEntry(level=level, message=message, details=details)
    await db.logs.insert_one(log_entry.dict())
    
    # Also log to console
    if level == "ERROR":
        logger.error(f"{message} - {details}")
    elif level == "WARNING":
        logger.warning(f"{message} - {details}")
    else:
        logger.info(f"{message} - {details}")

async def test_hyperliquid_connection():
    """Test connection to Hyperliquid"""
    try:
        info = hyperliquid_config.get_info_client()
        # Test with a simple call
        meta = info.meta()
        if meta:
            await log_message("INFO", "Hyperliquid connection successful", {"meta": meta})
            return True
        else:
            await log_message("ERROR", "Hyperliquid connection failed - no meta data")
            return False
    except Exception as e:
        await log_message("ERROR", f"Hyperliquid connection failed: {str(e)}")
        return False

async def discover_associated_accounts(wallet_address):
    """Discover all accounts associated with a wallet address"""
    try:
        info = hyperliquid_config.get_info_client()
        associated_accounts = [wallet_address]  # Always include the main wallet
        
        await log_message("INFO", f"Discovering accounts for wallet: {wallet_address}")
        
        # Check wallet role
        try:
            user_role_response = info.post("/info", {"type": "userRole", "user": wallet_address})
            await log_message("INFO", f"Wallet role: {user_role_response}")
            
            # If this is an agent wallet, extract the main user address
            if (user_role_response and 
                isinstance(user_role_response, dict) and 
                user_role_response.get('role') == 'agent' and 
                'data' in user_role_response and 
                'user' in user_role_response['data']):
                
                main_user_address = user_role_response['data']['user']
                associated_accounts.append(main_user_address)
                await log_message("INFO", f"Found main user account from agent: {main_user_address}")
                
        except Exception as e:
            await log_message("WARNING", f"Could not get user role: {str(e)}")
        
        # Get sub-accounts if this is a master account
        try:
            sub_accounts_data = info.post("/info", {"type": "subAccounts", "user": wallet_address})
            await log_message("INFO", f"Sub-accounts response: {sub_accounts_data}")
            
            if sub_accounts_data and isinstance(sub_accounts_data, list):
                for sub_account in sub_accounts_data:
                    if isinstance(sub_account, dict) and 'subAccountUser' in sub_account:
                        sub_address = sub_account['subAccountUser']
                        associated_accounts.append(sub_address)
                        await log_message("INFO", f"Found sub-account: {sub_address}")
                        
        except Exception as e:
            await log_message("WARNING", f"Could not get sub-accounts: {str(e)}")
        
        # Check for vault associations
        try:
            vault_data = info.post("/info", {"type": "userVaultEquities", "user": wallet_address})
            await log_message("INFO", f"Vault data response: {vault_data}")
            
            if vault_data and isinstance(vault_data, list):
                for vault_info in vault_data:
                    if isinstance(vault_info, dict) and 'vault' in vault_info:
                        vault_address = vault_info['vault']
                        associated_accounts.append(vault_address)
                        await log_message("INFO", f"Found vault: {vault_address}")
                        
        except Exception as e:
            await log_message("WARNING", f"Could not get vault data: {str(e)}")
        
        # Remove duplicates
        unique_accounts = list(set(associated_accounts))
        await log_message("INFO", f"Total unique accounts found: {len(unique_accounts)} - {unique_accounts}")
        
        return unique_accounts
        
    except Exception as e:
        await log_message("ERROR", f"Error discovering accounts: {str(e)}")
        return [wallet_address]  # Return at least the main wallet

async def find_account_with_balance():
    """Try to find the correct account address that has balance"""
    try:
        if not hyperliquid_config.private_key:
            return None, 0.0
            
        from eth_account import Account
        account = Account.from_key(hyperliquid_config.private_key)
        wallet_address = account.address
        
        info = hyperliquid_config.get_info_client()
        
        await log_message("INFO", f"Searching for account with balance...")
        
        # Discover all associated accounts
        addresses_to_try = await discover_associated_accounts(wallet_address)
        
        for address in addresses_to_try:
            try:
                await log_message("INFO", f"Checking balance for address: {address}")
                
                # Check perps balance
                user_state = info.user_state(address)
                margin_balance = float(user_state.get('marginSummary', {}).get('accountValue', '0.0'))
                
                # Check spot balance  
                spot_state = info.spot_user_state(address)
                spot_balance = 0.0
                if spot_state and 'balances' in spot_state:
                    for balance_info in spot_state['balances']:
                        if balance_info.get('coin') == 'USDC':
                            spot_balance += float(balance_info.get('total', 0))
                
                total_balance = margin_balance + spot_balance
                
                await log_message("INFO", f"Address {address}: Perps=${margin_balance}, Spot=${spot_balance}, Total=${total_balance}")
                
                if total_balance > 0:
                    await log_message("INFO", f"✅ Found account with balance: {address}")
                    return address, total_balance
                    
            except Exception as e:
                await log_message("WARNING", f"Error checking address {address}: {str(e)}")
                continue
        
        await log_message("WARNING", "No account with balance found in discovered accounts")
        return None, 0.0
        
    except Exception as e:
        await log_message("ERROR", f"Error in find_account_with_balance: {str(e)}")
        return None, 0.0

# Cache for balance to avoid rate limiting
balance_cache = {
    "balance": None,
    "address": None,
    "timestamp": None,
    "expires_in": 30  # seconds
}

async def get_cached_balance():
    """Get balance from cache or fetch if expired"""
    global balance_cache
    
    current_time = get_brazil_time().timestamp()
    
    # Check if cache is valid
    if (balance_cache["timestamp"] and 
        (current_time - balance_cache["timestamp"]) < balance_cache["expires_in"] and
        balance_cache["balance"] is not None):
        
        await log_message("INFO", f"Using cached balance: ${balance_cache['balance']}")
        return balance_cache["address"], balance_cache["balance"]
    
    # Cache expired or empty, fetch new data
    try:
        address, balance = await find_account_with_balance()
        
        # Update cache
        balance_cache["balance"] = balance
        balance_cache["address"] = address
        balance_cache["timestamp"] = current_time
        
        await log_message("INFO", f"Updated balance cache: ${balance}")
        return address, balance
        
    except Exception as e:
        await log_message("ERROR", f"Error fetching balance: {str(e)}")
        # Return cached data if available, even if expired
        if balance_cache["balance"] is not None:
            await log_message("INFO", f"Returning stale cache due to error: ${balance_cache['balance']}")
            return balance_cache["address"], balance_cache["balance"]
        return None, None

async def get_account_balance():
    """Get Hyperliquid exchange account balance with caching"""
    try:
        address, balance = await get_cached_balance()
        return balance
                
    except Exception as e:
        await log_message("ERROR", f"Failed to get account balance: {str(e)}")
        return None

async def get_wallet_address():
    """Get the correct wallet address with caching"""
    try:
        address, balance = await get_cached_balance()
        return address
        
    except Exception as e:
        await log_message("ERROR", f"Failed to get wallet address: {str(e)}")
        return None
    """Get Hyperliquid exchange account balance (trying different methods)"""
    try:
        if not hyperliquid_config.private_key:
            await log_message("WARNING", "No private key configured")
            return None
            
        # Get user address from private key for connection
        from eth_account import Account
        account = Account.from_key(hyperliquid_config.private_key)
        user_address = account.address
        
        await log_message("INFO", f"Connecting with wallet address: {user_address}")
        
        info = hyperliquid_config.get_info_client()
        
        # Method 1: Query the wallet address directly (current approach)
        try:
            await log_message("INFO", "Method 1: Querying wallet address directly...")
            user_state = info.user_state(user_address)
            await log_message("INFO", f"Direct wallet query result: {user_state}")
            
            if user_state and user_state.get('marginSummary', {}).get('accountValue', '0.0') != '0.0':
                balance = float(user_state['marginSummary']['accountValue'])
                await log_message("INFO", f"Found balance via direct wallet query: ${balance}")
                return balance
        except Exception as e:
            await log_message("WARNING", f"Method 1 failed: {str(e)}")
        
        # Method 2: Try to get account info through exchange client (might reveal account address)
        try:
            await log_message("INFO", "Method 2: Using Exchange client to find account...")
            exchange = hyperliquid_config.get_exchange_client()
            
            # Check if exchange object has account information
            if hasattr(exchange, 'account_address') and exchange.account_address:
                await log_message("INFO", f"Found exchange account address: {exchange.account_address}")
                # Query the exchange account address
                exchange_user_state = info.user_state(exchange.account_address)
                await log_message("INFO", f"Exchange account state: {exchange_user_state}")
                
                if exchange_user_state and exchange_user_state.get('marginSummary', {}).get('accountValue', '0.0') != '0.0':
                    balance = float(exchange_user_state['marginSummary']['accountValue'])
                    await log_message("INFO", f"Found balance via exchange account: ${balance}")
                    return balance
                    
        except Exception as e:
            await log_message("WARNING", f"Method 2 failed: {str(e)}")
        
        # Method 3: Try querying without specifying an address (let it use default)
        try:
            await log_message("INFO", "Method 3: Attempting to get current user info...")
            
            # Try to get current user positions or account info
            all_mids = info.all_mids()
            await log_message("INFO", f"Available markets: {len(all_mids) if all_mids else 0}")
            
            # Try to get open orders (this might reveal the actual account)
            try:
                orders = info.open_orders(user_address)
                await log_message("INFO", f"Open orders for wallet: {orders}")
            except Exception as order_error:
                await log_message("INFO", f"No open orders or error: {str(order_error)}")
            
        except Exception as e:
            await log_message("WARNING", f"Method 3 failed: {str(e)}")
        
        # Method 4: Check if there are any sub-accounts or related addresses
        try:
            await log_message("INFO", "Method 4: Checking for sub-accounts...")
            
            # Try some common derived addresses (this is speculative)
            # Sometimes accounts use deterministic derivation
            
            await log_message("INFO", f"Primary wallet address being queried: {user_address}")
            
            # Last attempt - fresh query with detailed logging
            final_state = info.user_state(user_address)
            if final_state:
                await log_message("INFO", f"FINAL STATE DETAILS:")
                await log_message("INFO", f"  marginSummary: {final_state.get('marginSummary', {})}")
                await log_message("INFO", f"  crossMarginSummary: {final_state.get('crossMarginSummary', {})}")
                await log_message("INFO", f"  withdrawable: {final_state.get('withdrawable', '0.0')}")
                await log_message("INFO", f"  assetPositions: {final_state.get('assetPositions', [])}")
                
                # Check spot account one more time
                spot_state = info.spot_user_state(user_address)
                await log_message("INFO", f"  SPOT STATE: {spot_state}")
                
                # Return any non-zero balance found
                margin_balance = float(final_state.get('marginSummary', {}).get('accountValue', '0.0'))
                withdrawable = float(final_state.get('withdrawable', '0.0'))
                
                if margin_balance > 0:
                    return margin_balance
                elif withdrawable > 0:
                    return withdrawable
                    
        except Exception as e:
            await log_message("ERROR", f"Method 4 failed: {str(e)}")
        
        await log_message("WARNING", "All methods exhausted - no balance found")
        return None
                
    except Exception as e:
        await log_message("ERROR", f"Failed to get account balance: {str(e)}")
        return None

# API Endpoints
@api_router.post("/webhook/tradingview")
async def handle_tradingview_webhook(request: Request):
    """Handle incoming TradingView webhook"""
    try:
        # Get raw body first for debugging
        raw_body = await request.body()
        content_type = request.headers.get("content-type", "")
        
        # Log raw webhook data with better formatting
        raw_body_str = raw_body.decode('utf-8', errors='replace')
        
        await log_message("INFO", "=== WEBHOOK RECEIVED ===")
        await log_message("INFO", f"Content-Type: {content_type}")
        await log_message("INFO", f"Body Length: {len(raw_body)} bytes")
        await log_message("INFO", f"Raw Body (first 500 chars): {raw_body_str[:500]}")
        await log_message("INFO", f"Raw Body (full): {raw_body_str}")
        
        # Try to parse JSON
        try:
            payload = await request.json()
            await log_message("INFO", "✅ JSON PARSING SUCCESS")
            await log_message("INFO", f"Parsed Payload: {payload}")
        except Exception as json_error:
            await log_message("ERROR", "❌ JSON PARSING FAILED")
            await log_message("ERROR", f"JSON Error: {str(json_error)}")
            await log_message("ERROR", f"Error Type: {type(json_error).__name__}")
            await log_message("ERROR", f"Full Raw Body: '{raw_body_str}'")
            await log_message("ERROR", f"Body as bytes: {list(raw_body)}")
            await log_message("ERROR", f"Body hex: {raw_body.hex()}")
            
            # Try to handle common JSON issues
            try:
                await log_message("INFO", "⚠️ ATTEMPTING JSON CLEANUP")
                # Remove any potential BOM or invalid characters
                cleaned_body = raw_body.decode('utf-8-sig', errors='replace').strip()
                await log_message("INFO", f"Cleaned Body: '{cleaned_body}'")
                
                if cleaned_body:
                    import json
                    payload = json.loads(cleaned_body)
                    await log_message("INFO", "✅ JSON CLEANUP SUCCESS")
                    await log_message("INFO", f"Cleaned Payload: {payload}")
                else:
                    await log_message("ERROR", "❌ EMPTY BODY AFTER CLEANUP")
                    raise ValueError("Empty body after cleanup")
            except Exception as cleanup_error:
                await log_message("ERROR", "❌ JSON CLEANUP FAILED")
                await log_message("ERROR", f"Cleanup Error: {str(cleanup_error)}")
                await log_message("ERROR", f"Cleanup Error Type: {type(cleanup_error).__name__}")
                
                # Try one more approach - character by character analysis
                await log_message("INFO", "🔍 CHARACTER ANALYSIS")
                if len(raw_body_str) > 0:
                    for i, char in enumerate(raw_body_str[:100]):  # First 100 chars
                        char_info = f"Index {i}: '{char}' (ord: {ord(char)}, hex: {hex(ord(char))})"
                        await log_message("INFO", char_info)
                
                stats['failed_forwards'] += 1
                raise HTTPException(
                    status_code=400, 
                    detail=f"Invalid JSON format: {str(json_error)}"
                )
        
        # Validate payload structure
        if not isinstance(payload, dict):
            await log_message("ERROR", "❌ PAYLOAD VALIDATION FAILED")
            await log_message("ERROR", f"Payload Type: {type(payload)}")
            await log_message("ERROR", f"Payload Value: {payload}")
            stats['failed_forwards'] += 1
            raise HTTPException(status_code=400, detail="Payload must be a JSON object")
        
        # Log successful webhook processing
        await log_message("INFO", "✅ WEBHOOK VALIDATION SUCCESS")
        await log_message("INFO", f"Final Payload: {payload}")
        
        # Log the incoming webhook
        webhook_msg = WebhookMessage(payload=payload)
        await db.webhooks.insert_one(webhook_msg.dict())
        stats['total_webhooks'] += 1
        
        await log_message("INFO", f"✅ WEBHOOK STORED: {webhook_msg.id}")
        
        # Forward to Hyperliquid
        try:
            await log_message("INFO", "🚀 FORWARDING TO HYPERLIQUID")
            hyperliquid_response = await forward_to_hyperliquid(webhook_msg.id, payload)
            stats['successful_forwards'] += 1
            
            await log_message("INFO", "✅ HYPERLIQUID FORWARD SUCCESS")
            await log_message("INFO", f"Hyperliquid Response: {hyperliquid_response}")
            
            return {
                "status": "success",
                "webhook_id": webhook_msg.id,
                "message": "Webhook processed and forwarded to Hyperliquid",
                "hyperliquid_response": hyperliquid_response
            }
            
        except Exception as forward_error:
            await log_message("ERROR", "❌ HYPERLIQUID FORWARD FAILED")
            await log_message("ERROR", f"Forward Error: {str(forward_error)}")
            await log_message("ERROR", f"Forward Error Type: {type(forward_error).__name__}")
            await log_message("ERROR", f"Webhook ID: {webhook_msg.id}")
            await log_message("ERROR", f"Payload: {payload}")
            stats['failed_forwards'] += 1
            
            return {
                "status": "error",
                "webhook_id": webhook_msg.id,
                "message": f"Webhook processing failed: {str(forward_error)}",
                "error": str(forward_error)
            }
            
    except HTTPException:
        raise
    except Exception as e:
        await log_message("ERROR", "❌ WEBHOOK HANDLER FATAL ERROR")
        await log_message("ERROR", f"Fatal Error: {str(e)}")
        await log_message("ERROR", f"Fatal Error Type: {type(e).__name__}")
        stats['failed_forwards'] += 1
        raise HTTPException(
            status_code=500, 
            detail=f"Webhook processing failed: {str(e)}"
        )

async def get_asset_info(symbol: str):
    """Get asset metadata from Hyperliquid including szDecimals"""
    try:
        info = hyperliquid_config.get_info_client()
        
        # Get asset metadata
        meta_data = info.post("/info", {"type": "meta"})
        
        await log_message("INFO", f"📊 Retrieved asset metadata for {symbol}")
        
        # Find asset in universe (perpetual contracts)
        asset_info = None
        if meta_data and "universe" in meta_data:
            for asset in meta_data["universe"]:
                if asset["name"] == symbol:
                    asset_info = asset
                    break
        
        # If not found in universe, check tokens
        if not asset_info and meta_data and "tokens" in meta_data:
            for token in meta_data["tokens"]:
                if token["name"] == symbol:
                    asset_info = token
                    break
        
        if asset_info:
            # For perpetual contracts, get szDecimals from tokens
            if "tokens" in asset_info:
                # This is a perpetual contract like "SOL/USDC"
                token_index = asset_info["tokens"][0]  # First token is the base asset
                if token_index < len(meta_data["tokens"]):
                    token_info = meta_data["tokens"][token_index]
                    sz_decimals = token_info.get("szDecimals", 3)
                    await log_message("INFO", f"📏 {symbol} perpetual szDecimals: {sz_decimals}")
                    return sz_decimals
            else:
                # This is a spot token
                sz_decimals = asset_info.get("szDecimals", 3)
                await log_message("INFO", f"📏 {symbol} spot szDecimals: {sz_decimals}")
                return sz_decimals
        
        # Default fallback
        await log_message("WARNING", f"⚠️ Asset {symbol} not found in metadata, using default szDecimals: 3")
        return 3
        
    except Exception as e:
        await log_message("ERROR", f"❌ Error getting asset info for {symbol}: {str(e)}")
        return 3  # Default fallback

def calculate_quantity_from_usd(usd_amount: float, price: float, sz_decimals: int) -> float:
    """Calculate quantity from USD amount and round to szDecimals"""
    try:
        # Calculate raw quantity
        raw_quantity = usd_amount / price
        
        # Round to szDecimals
        quantity = round(raw_quantity, sz_decimals)
        
        return quantity
        
    except Exception as e:
        return round(usd_amount / price, 3)  # Fallback

def format_quantity(quantity: float, sz_decimals: int) -> float:
    """Format quantity to use maximum allowed decimal places based on szDecimals"""
    # Always use the maximum decimal places allowed by szDecimals
    return round(quantity, sz_decimals)

async def forward_to_hyperliquid(webhook_id: str, payload: Dict[str, Any]):
    """Forward the webhook payload to Hyperliquid and execute real trades"""
    try:
        await log_message("INFO", f"🚀 Processing TradingView webhook {webhook_id}")
        await log_message("INFO", f"📊 Payload received: {payload}")
        
        # Parse the TradingView payload - NEW FORMAT
        symbol = payload.get("symbol", "").upper()  # SOL, BTC, ETH, etc.
        side = payload.get("side", "").lower()  # buy/sell
        entry_type = payload.get("entry", "market").lower()  # market/limit
        raw_quantity = float(payload.get("quantity", 0))
        raw_price = float(payload.get("price", 0)) if payload.get("price") else None  # Price for limit orders
        stop_price = float(payload.get("stop", 0)) if payload.get("stop") else None  # Stop loss price
        
        # Get asset information from Hyperliquid
        await log_message("INFO", f"🔍 Getting asset info for {symbol}")
        sz_decimals = await get_asset_info(symbol)
        
        # Format quantity based on szDecimals
        quantity = format_quantity(raw_quantity, sz_decimals)
        
        # Format price to avoid tick size issues
        if raw_price:
            if symbol in ["SOL", "ETH", "AVAX"]:
                # For SOL/ETH/AVAX, round to nearest 0.05 or 0.1
                # Test different rounding strategies
                price_rounded_05 = round(raw_price * 20) / 20  # Round to nearest 0.05
                price_rounded_10 = round(raw_price * 10) / 10  # Round to nearest 0.10
                price_rounded_25 = round(raw_price * 4) / 4    # Round to nearest 0.25
                price_rounded_50 = round(raw_price * 2) / 2    # Round to nearest 0.50
                price_rounded_100 = round(raw_price)           # Round to nearest 1.00
                
                # Try different rounding methods, start with most precise
                possible_prices = [price_rounded_05, price_rounded_10, price_rounded_25, price_rounded_50, price_rounded_100]
                price = possible_prices[3]  # Try 0.50 rounding
                
                await log_message("INFO", f"Price formatting options for {symbol}:")
                await log_message("INFO", f"  Original: {raw_price}")
                await log_message("INFO", f"  Rounded to 0.05: {price_rounded_05}")
                await log_message("INFO", f"  Rounded to 0.10: {price_rounded_10}")
                await log_message("INFO", f"  Rounded to 0.25: {price_rounded_25}")
                await log_message("INFO", f"  Rounded to 0.50: {price_rounded_50}")
                await log_message("INFO", f"  Rounded to 1.00: {price_rounded_100}")
                await log_message("INFO", f"  Selected: {price}")
                
            elif symbol in ["BTC"]:
                # For BTC, round to nearest 10 or 100
                price = round(raw_price, -1)  # Round to nearest 10
            else:
                # For other tokens, round to 4 decimal places
                price = round(raw_price, 4)
        else:
            price = None
        
        # Ensure quantity meets minimum size (0.1 of the smallest unit)
        min_size = 10 ** (-sz_decimals + 1) if sz_decimals > 1 else 0.1
        if quantity < min_size:
            raise ValueError(f"Quantity {quantity} is below minimum size {min_size} for {symbol} (szDecimals: {sz_decimals})")
        
        # Additional validation: ensure quantity is not too large
        if quantity > 1000:
            raise ValueError(f"Quantity {quantity} is too large. Maximum allowed: 1000")
        
        await log_message("INFO", f"📋 Parsed and validated fields:")
        await log_message("INFO", f"  Symbol: {symbol}")
        await log_message("INFO", f"  Side: {side}")
        await log_message("INFO", f"  Entry Type: {entry_type}")
        await log_message("INFO", f"  Raw Quantity: {raw_quantity} → Formatted: {quantity} (szDecimals: {sz_decimals})")
        await log_message("INFO", f"  Raw Price: {raw_price} → Formatted: {price}")
        await log_message("INFO", f"  Stop Price: {stop_price}")
        await log_message("INFO", f"  Min Size: {min_size}")
        
        # Validate required fields
        if not symbol:
            raise ValueError("Missing required field: symbol")
        if not side or side not in ["buy", "sell"]:
            raise ValueError(f"Invalid or missing side: {side}. Must be 'buy' or 'sell'")
        if quantity <= 0:
            raise ValueError(f"Invalid quantity: {quantity}. Must be > 0")
        if entry_type not in ["market", "limit"]:
            raise ValueError(f"Invalid entry type: {entry_type}. Must be 'market' or 'limit'")
        if entry_type == "limit" and (not price or price <= 0):
            raise ValueError(f"Limit order requires valid price. Got: {price}")
        
        # Convert side to Hyperliquid format
        is_buy = (side == "buy")
        
        await log_message("INFO", f"✅ Validation passed - Executing {entry_type} {side} order")
        
        # Get exchange client
        exchange = hyperliquid_config.get_exchange_client()
        
        # Prepare order parameters
        order_params = {
            "name": symbol,
            "is_buy": is_buy,
            "sz": quantity,
            "reduce_only": False
        }
        
        # Set order type based on entry type
        if entry_type == "market":
            await log_message("INFO", f"🎯 Executing MARKET order: {side} {quantity} {symbol}")
            order_params["order_type"] = {"market": {}}
        else:  # limit
            await log_message("INFO", f"🎯 Executing LIMIT order: {side} {quantity} {symbol} @ ${price}")
            order_params["order_type"] = {"limit": {"tif": "Gtc"}}
            order_params["limit_px"] = price
        
        await log_message("INFO", f"📤 Order parameters: {order_params}")
        
        # Execute the order with automatic retry for different price formats
        order_executed = False
        last_error = None
        main_order_result = None
        
        for attempt in range(5):  # Try up to 5 different price formats
            try:
                # Adjust price format for each attempt
                if entry_type == "market":
                    if attempt == 0:
                        market_price = price * 1.02 if (price and is_buy) else price * 0.98 if price else 170  # 2% buffer
                    elif attempt == 1:
                        market_price = round(price * 2) / 2 if price else 170  # Round to 0.5
                    elif attempt == 2:
                        market_price = round(price) if price else 170  # Round to 1.0
                    elif attempt == 3:
                        market_price = round(price * 4) / 4 if price else 170  # Round to 0.25
                    else:
                        market_price = round(price * 10) / 10 if price else 170  # Round to 0.1
                    
                    await log_message("INFO", f"Attempt {attempt + 1}: Market price ${market_price}")
                    
                    result = exchange.order(
                        name=symbol,
                        is_buy=is_buy,
                        sz=quantity,
                        limit_px=market_price,
                        order_type={"limit": {"tif": "Ioc"}},
                        reduce_only=False
                    )
                else:  # limit
                    # Try different price roundings for limit orders
                    if attempt == 0:
                        limit_price = round(price * 2) / 2  # Round to 0.5
                    elif attempt == 1:
                        limit_price = round(price)  # Round to 1.0
                    elif attempt == 2:
                        limit_price = round(price * 4) / 4  # Round to 0.25
                    elif attempt == 3:
                        limit_price = round(price * 10) / 10  # Round to 0.1
                    else:
                        limit_price = round(price * 20) / 20  # Round to 0.05
                    
                    await log_message("INFO", f"Attempt {attempt + 1}: Limit price ${limit_price}")
                    
                    result = exchange.order(
                        name=symbol,
                        is_buy=is_buy,
                        sz=quantity,
                        limit_px=limit_price,
                        order_type={"limit": {"tif": "Gtc"}},
                        reduce_only=False
                    )
                
                # Check if order was successful
                if result and result.get("status") == "ok":
                    statuses = result.get("response", {}).get("data", {}).get("statuses", [])
                    if statuses and not any("error" in status for status in statuses):
                        await log_message("INFO", f"✅ Order executed successfully on attempt {attempt + 1}")
                        order_executed = True
                        break
                    else:
                        error_msg = statuses[0].get("error", "Unknown error") if statuses else "Unknown error"
                        await log_message("WARNING", f"Attempt {attempt + 1} failed: {error_msg}")
                        last_error = error_msg
                        continue
                
            except Exception as order_error:
                await log_message("WARNING", f"Attempt {attempt + 1} exception: {str(order_error)}")
                last_error = str(order_error)
                continue
        
        if order_executed:
            await log_message("INFO", f"✅ Hyperliquid order executed successfully after {attempt + 1} attempts!")
            await log_message("INFO", f"📈 Order result: {result}")
            main_order_result = result
            
            # Place stop loss order if stop_price is provided
            stop_order_result = None
            if stop_price:
                await log_message("INFO", f"🛑 Setting up stop loss order at ${stop_price}")
                try:
                    # For stop loss: if we bought, sell at stop price; if we sold, buy at stop price
                    stop_is_buy = not is_buy  # Opposite of main order
                    
                    # Format stop price similar to main order
                    if symbol in ["SOL", "ETH", "AVAX"]:
                        formatted_stop_price = round(stop_price * 2) / 2  # Round to nearest 0.50
                    elif symbol in ["BTC"]:
                        formatted_stop_price = round(stop_price, -1)  # Round to nearest 10
                    else:
                        formatted_stop_price = round(stop_price, 4)
                    
                    await log_message("INFO", f"🛑 Placing stop loss: {'BUY' if stop_is_buy else 'SELL'} {quantity} {symbol} at trigger ${formatted_stop_price}")
                    
                    # Place stop loss order using trigger order type
                    stop_order_result = exchange.order(
                        name=symbol,
                        is_buy=stop_is_buy,
                        sz=quantity,
                        limit_px=formatted_stop_price,
                        order_type={
                            "trigger": {
                                "triggerPx": formatted_stop_price,  # Changed from "trigger_px" to "triggerPx"
                                "isMarket": True,
                                "tpsl": "sl"  # Stop loss
                            }
                        },
                        reduce_only=True  # Only reduce existing position
                    )
                    
                    if stop_order_result and stop_order_result.get("status") == "ok":
                        await log_message("INFO", f"✅ Stop loss order placed successfully!")
                        await log_message("INFO", f"🛑 Stop loss result: {stop_order_result}")
                    else:
                        await log_message("ERROR", f"❌ Failed to place stop loss order: {stop_order_result}")
                    
                except Exception as stop_error:
                    await log_message("ERROR", f"❌ Error placing stop loss order: {str(stop_error)}")
                    stop_order_result = {"error": str(stop_error)}
            
            # Prepare successful response
            response_data = {
                "status": "success",
                "message": "Order executed successfully on Hyperliquid",
                "environment": hyperliquid_config.environment,
                "timestamp": get_brazil_time().isoformat(),
                "order_details": {
                    "symbol": symbol,
                    "side": side,
                    "entry_type": entry_type,
                    "quantity": quantity,
                    "price": price,
                    "stop_price": stop_price,
                    "attempts": attempt + 1,
                    "hyperliquid_response": main_order_result,
                    "stop_loss_response": stop_order_result
                },
                "original_payload": payload
            }
        else:
            await log_message("ERROR", f"❌ All attempts failed. Last error: {last_error}")
            
            # Prepare error response
            response_data = {
                "status": "error",
                "message": f"Order execution failed after 5 attempts: {last_error}",
                "environment": hyperliquid_config.environment,
                "timestamp": get_brazil_time().isoformat(),
                "order_details": {
                    "symbol": symbol,
                    "side": side,
                    "entry_type": entry_type,
                    "quantity": quantity,
                    "price": price,
                    "stop_price": stop_price,
                    "attempts": 5
                },
                "error": last_error,
                "original_payload": payload
            }
        
        # Store the response
        hl_response = HyperliquidResponse(
            webhook_id=webhook_id,
            response_data=response_data
        )
        await db.hyperliquid_responses.insert_one(hl_response.dict())
        
        await log_message("INFO", f"💾 Response stored with webhook_id: {webhook_id}")
        
        return response_data
        
    except Exception as e:
        error_msg = f"Failed to process webhook for Hyperliquid: {str(e)}"
        await log_message("ERROR", f"❌ Fatal error in forward_to_hyperliquid: {error_msg}")
        await log_message("ERROR", f"❌ Error type: {type(e).__name__}")
        
        # Store error response
        error_response = {
            "status": "error",
            "message": error_msg,
            "environment": hyperliquid_config.environment,
            "timestamp": get_brazil_time().isoformat(),
            "error": str(e),
            "original_payload": payload
        }
        
        hl_response = HyperliquidResponse(
            webhook_id=webhook_id,
            response_data=error_response
        )
        await db.hyperliquid_responses.insert_one(hl_response.dict())
        
        return error_response

@api_router.get("/status")
async def get_server_status():
    """Get server status and statistics"""
    try:
        # Test Hyperliquid connection
        hl_connected = await test_hyperliquid_connection()
        
        # Get account balance
        balance = await get_account_balance()
        
        # Get wallet address
        wallet_address = await get_wallet_address()
        
        # Calculate uptime
        uptime = get_brazil_time() - server_start_time
        uptime_str = f"{uptime.days}d {uptime.seconds//3600}h {(uptime.seconds//60)%60}m"
        
        status = ServerStatus(
            status="running",
            environment=hyperliquid_config.environment,
            timestamp=get_brazil_time(),
            uptime=uptime_str,
            total_webhooks=stats['total_webhooks'],
            successful_forwards=stats['successful_forwards'],
            failed_forwards=stats['failed_forwards'],
            hyperliquid_connected=hl_connected,
            balance=balance,
            wallet_address=wallet_address
        )
        
        return status
        
    except Exception as e:
        await log_message("ERROR", f"Failed to get server status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/logs")
async def get_logs(limit: int = 100, level: Optional[str] = None):
    """Get recent logs"""
    try:
        query = {}
        if level:
            query["level"] = level
            
        logs = await db.logs.find(query).sort("timestamp", -1).limit(limit).to_list(limit)
        
        # Convert to JSON-serializable format
        logs_data = []
        for log in logs:
            log_data = {
                "id": log.get("id"),
                "timestamp": log.get("timestamp"),
                "level": log.get("level"),
                "message": log.get("message"),
                "details": log.get("details")
            }
            logs_data.append(log_data)
            
        return {"logs": logs_data}
        
    except Exception as e:
        await log_message("ERROR", f"Failed to get logs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/webhooks")
async def get_webhooks(limit: int = 50):
    """Get recent webhooks"""
    try:
        webhooks = await db.webhooks.find().sort("timestamp", -1).limit(limit).to_list(limit)
        
        # Convert to JSON-serializable format
        webhooks_data = []
        for webhook in webhooks:
            webhook_data = {
                "id": webhook.get("id"),
                "timestamp": webhook.get("timestamp"),
                "source": webhook.get("source"),
                "payload": webhook.get("payload"),
                "status": webhook.get("status"),
                "error": webhook.get("error")
            }
            webhooks_data.append(webhook_data)
            
        return {"webhooks": webhooks_data}
        
    except Exception as e:
        await log_message("ERROR", f"Failed to get webhooks: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/restart")
async def restart_server():
    """Restart the server"""
    try:
        await log_message("INFO", "Server restart requested via API")
        
        # Add restart log
        restart_log = {
            "timestamp": get_brazil_time().isoformat(),
            "level": "INFO",
            "message": "Server restarting...",
            "details": "Restart requested via web interface"
        }
        
        # Store restart log in database
        await db.logs.insert_one(restart_log)
        
        import os
        import signal
        
        # Send restart signal to supervisor
        os.system("sudo supervisorctl restart backend")
        
        return {"status": "success", "message": "Server restart initiated"}
        
    except Exception as e:
        await log_message("ERROR", f"Failed to restart server: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Add startup log
@app.on_event("startup")
async def startup_event():
    """Log server startup"""
    await log_message("INFO", "TradingView to Hyperliquid middleware server started")
    await log_message("INFO", f"Server environment: {hyperliquid_config.environment}")
    await log_message("INFO", f"Server start time: {server_start_time}")
    await log_message("INFO", "Webhook endpoint available at /api/webhook/tradingview")

@api_router.get("/refresh-balance")
async def force_refresh_balance():
    """Force refresh account balance"""
    try:
        balance = await get_account_balance()
        wallet_address = await get_wallet_address()
        
        result = {
            "wallet_address": wallet_address,
            "balance": balance,
            "timestamp": get_brazil_time(),
            "message": "Balance refreshed successfully"
        }
        
        return result
        
    except Exception as e:
        await log_message("ERROR", f"Failed to refresh balance: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/responses")
async def get_hyperliquid_responses(limit: int = 50):
    """Get recent Hyperliquid responses"""
    try:
        responses = await db.hyperliquid_responses.find().sort("timestamp", -1).limit(limit).to_list(limit)
        
        # Convert to JSON-serializable format
        responses_data = []
        for response in responses:
            response_data = {
                "id": response.get("id"),
                "timestamp": response.get("timestamp"),
                "webhook_id": response.get("webhook_id"),
                "response_data": response.get("response_data"),
                "status": response.get("status"),
                "error": response.get("error")
            }
            responses_data.append(response_data)
            
        return {"responses": responses_data}
        
    except Exception as e:
        await log_message("ERROR", f"Failed to get responses: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/environment")
async def switch_environment(environment: str):
    """Switch between testnet and mainnet"""
    if environment not in ["testnet", "mainnet"]:
        raise HTTPException(status_code=400, detail="Environment must be 'testnet' or 'mainnet'")
    
    try:
        # Update environment
        global hyperliquid_config
        os.environ['ENVIRONMENT'] = environment
        hyperliquid_config = HyperliquidConfig()
        
        await log_message("INFO", f"Environment switched to {environment}")
        
        return {"status": "success", "environment": environment}
        
    except Exception as e:
        await log_message("ERROR", f"Failed to switch environment: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/environment")
async def get_environment():
    """Get current environment"""
    return {"environment": hyperliquid_config.environment}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Initialize the application"""
    await log_message("INFO", "TradingView to Hyperliquid Middleware Server Starting")
    await test_hyperliquid_connection()

@app.on_event("shutdown")
async def shutdown_db_client():
    await log_message("INFO", "Server shutting down")
    client.close()