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
    "expires_in": 300  # 5 minutes instead of 30 seconds
}

async def get_cached_balance():
    """Get balance from cache or fetch if expired"""
    global balance_cache
    
    current_time = get_brazil_time().timestamp()
    
    # Check if cache is valid
    if (balance_cache["timestamp"] and 
        (current_time - balance_cache["timestamp"]) < balance_cache["expires_in"] and
        balance_cache["balance"] is not None):
        
        # Only log cache usage occasionally to reduce log spam
        if current_time % 30 < 1:  # Log approximately every 30 seconds
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
@api_router.post("/webhook/re-execute")
async def re_execute_webhook(webhook_data: dict):
    """Re-execute a webhook payload for testing purposes"""
    try:
        await log_message("INFO", f"🔄 Re-executing webhook: {webhook_data}")
        
        # Extract payload from the webhook data
        payload = webhook_data.get('payload', {})
        
        if not payload:
            raise HTTPException(status_code=400, detail="No payload found in webhook data")
        
        # Process the webhook using the same logic as the original webhook
        webhook_id = str(uuid.uuid4())
        
        # Store the re-executed webhook
        webhook_message = WebhookMessage(
            id=webhook_id,
            source="re-execution",
            payload=payload
        )
        await db.webhooks.insert_one(webhook_message.dict())
        
        await log_message("INFO", f"📨 Re-executing webhook with ID: {webhook_id}")
        
        # Forward to Hyperliquid using the same logic
        hyperliquid_response = await forward_to_hyperliquid(webhook_id, payload)
        
        return {
            "status": "success",
            "message": "Webhook re-executed successfully",
            "webhook_id": webhook_id,
            "hyperliquid_response": hyperliquid_response
        }
        
    except Exception as e:
        await log_message("ERROR", f"Failed to re-execute webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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

async def get_open_positions_internal(symbol: str):
    """Internal helper function to get open positions for a specific symbol"""
    try:
        info = hyperliquid_config.get_info_client()
        
        # Get wallet address from cache
        wallet_address = await get_wallet_address()
        if not wallet_address:
            await log_message("WARNING", f"No wallet address found for position check")
            return []
        
        # Get user state to check positions
        user_state = info.user_state(wallet_address)
        
        if not user_state or 'assetPositions' not in user_state:
            await log_message("INFO", f"No positions found for {symbol}")
            return []
        
        # Find positions for the specific symbol
        positions = []
        for position in user_state['assetPositions']:
            if position.get('position', {}).get('coin') == symbol:
                position_data = position.get('position', {})
                size = float(position_data.get('szi', 0))
                
                if size != 0:  # Only include non-zero positions
                    # Debug logging to understand data types
                    entry_px = position_data.get('entryPx')
                    await log_message("INFO", f"Debug: entry_px type: {type(entry_px)}, value: {entry_px}")
                    
                    positions.append({
                        'symbol': symbol,
                        'size': size,
                        'entry_px': entry_px,
                        'unrealized_pnl': position_data.get('unrealizedPnl'),
                        'position_data': position_data
                    })
        
        await log_message("INFO", f"Found {len(positions)} open positions for {symbol}")
        for pos in positions:
            await log_message("INFO", f"  Position: {pos['size']} {symbol} @ {pos['entry_px']}")
        
        return positions
        
    except Exception as e:
        await log_message("ERROR", f"Error checking positions for {symbol}: {str(e)}")
        return []

async def clear_symbol_orders_and_positions(symbol: str, webhook_id: str):
    """Cancel all open orders and close all positions for a specific symbol"""
    try:
        exchange = hyperliquid_config.get_exchange_client()
        info = hyperliquid_config.get_info_client()
        
        # Get wallet address from cache
        wallet_address = await get_wallet_address()
        if not wallet_address:
            await log_message("WARNING", f"No wallet address found for clearing {symbol}")
            return True
        
        await log_message("INFO", f"🧹 Clearing all orders and positions for {symbol}")
        
        # STEP 1: Close all positions FIRST (this removes stop orders automatically)
        try:
            user_state = info.user_state(wallet_address)
            
            if user_state and 'assetPositions' in user_state:
                positions_found = False
                for position in user_state['assetPositions']:
                    if position.get('position', {}).get('coin') == symbol:
                        position_data = position.get('position', {})
                        size = float(position_data.get('szi', 0))
                        
                        if size != 0:  # Only close non-zero positions
                            positions_found = True
                            # Determine the side to close the position
                            is_buy = size < 0  # Buy to close short, sell to close long
                            close_quantity = abs(size)
                            
                            await log_message("INFO", f"🔄 Closing position: {size} {symbol} using market_close")
                            
                            try:
                                # Use market_close method which automatically handles position sizing
                                close_result = exchange.market_close(
                                    coin=symbol,
                                    sz=None,  # Let it close the entire position automatically
                                    px=None,  # Let it use market price
                                    slippage=0.05,  # 5% slippage tolerance
                                    cloid=None
                                )
                                
                                # Check if the close was actually successful
                                is_successful = False
                                error_message = None
                                
                                if close_result and close_result.get("status") == "ok":
                                    # Check the actual order status in the response
                                    response_data = close_result.get("response", {})
                                    if response_data.get("type") == "order":
                                        statuses = response_data.get("data", {}).get("statuses", [])
                                        
                                        for status in statuses:
                                            if "error" in status:
                                                error_message = status["error"]
                                                break
                                            elif "filled" in status or "resting" in status:
                                                is_successful = True
                                                break
                                
                                # Store the REAL Hyperliquid response with correct success/error
                                close_response_data = {
                                    "status": "success" if is_successful else "error",
                                    "message": f"Market close response for {symbol}",
                                    "operation": "close_position",
                                    "environment": hyperliquid_config.environment,
                                    "timestamp": get_brazil_time().isoformat(),
                                    "position_details": {
                                        "symbol": symbol,
                                        "original_size": size,
                                        "close_method": "market_close",
                                        "slippage": 0.05
                                    },
                                    "hyperliquid_response": close_result,  # REAL response from Hyperliquid
                                    "error": error_message if error_message else None
                                }
                                
                                close_hl_response = HyperliquidResponse(
                                    webhook_id=webhook_id,
                                    response_data=close_response_data
                                )
                                await db.hyperliquid_responses.insert_one(close_hl_response.dict())
                                
                                if is_successful:
                                    await log_message("INFO", f"✅ Position closed with market_close: {size} {symbol}")
                                else:
                                    await log_message("ERROR", f"❌ Failed to close position {size} {symbol}: {error_message or 'Unknown error'}")
                                    
                            except Exception as e:
                                await log_message("ERROR", f"❌ Exception closing position {size} {symbol}: {str(e)}")
                                
                                # Store the error response
                                error_response_data = {
                                    "status": "error",
                                    "message": f"Exception closing position {size} {symbol}",
                                    "operation": "close_position",
                                    "environment": hyperliquid_config.environment,
                                    "timestamp": get_brazil_time().isoformat(),
                                    "error": str(e),
                                    "position_details": {
                                        "symbol": symbol,
                                        "original_size": size,
                                        "close_method": "market_close"
                                    }
                                }
                                
                                error_hl_response = HyperliquidResponse(
                                    webhook_id=webhook_id,
                                    response_data=error_response_data
                                )
                                await db.hyperliquid_responses.insert_one(error_hl_response.dict())
                
                if not positions_found:
                    await log_message("INFO", f"No positions found for {symbol}")
                    
                    # Store response indicating no positions to close
                    no_positions_response_data = {
                        "status": "info",
                        "message": f"No positions found for {symbol}",
                        "operation": "close_position",
                        "environment": hyperliquid_config.environment,
                        "timestamp": get_brazil_time().isoformat(),
                        "position_details": {
                            "symbol": symbol,
                            "positions_found": 0
                        }
                    }
                    
                    no_positions_hl_response = HyperliquidResponse(
                        webhook_id=webhook_id,
                        response_data=no_positions_response_data
                    )
                    await db.hyperliquid_responses.insert_one(no_positions_hl_response.dict())
                    
            else:
                await log_message("INFO", f"No positions found for {symbol}")
                
                # Store response indicating no positions to close
                no_positions_response_data = {
                    "status": "info",
                    "message": f"No positions found for {symbol}",
                    "operation": "close_position",
                    "environment": hyperliquid_config.environment,
                    "timestamp": get_brazil_time().isoformat(),
                    "position_details": {
                        "symbol": symbol,
                        "positions_found": 0
                    }
                }
                
                no_positions_hl_response = HyperliquidResponse(
                    webhook_id=webhook_id,
                    response_data=no_positions_response_data
                )
                await db.hyperliquid_responses.insert_one(no_positions_hl_response.dict())
                
        except Exception as e:
            await log_message("ERROR", f"Error checking/closing positions for {symbol}: {str(e)}")
            
            # Store error response
            error_response_data = {
                "status": "error",
                "message": f"Error checking positions for {symbol}",
                "operation": "close_position",
                "environment": hyperliquid_config.environment,
                "timestamp": get_brazil_time().isoformat(),
                "error": str(e),
                "symbol": symbol
            }
            
            error_hl_response = HyperliquidResponse(
                webhook_id=webhook_id,
                response_data=error_response_data
            )
            await db.hyperliquid_responses.insert_one(error_hl_response.dict())
        
        # STEP 2: Cancel remaining orders AFTER closing positions (cleans up orphaned orders)
        try:
            open_orders = info.open_orders(wallet_address)
            symbol_orders = [order for order in open_orders if order.get('coin') == symbol]
            
            if symbol_orders:
                await log_message("INFO", f"Found {len(symbol_orders)} remaining orders for {symbol}")
                
                for order in symbol_orders:
                    order_id = order.get('oid')
                    side = order.get('side')
                    size = order.get('sz')
                    price = order.get('limitPx')
                    
                    await log_message("INFO", f"🚫 Canceling remaining order: {symbol} {side} {size} @ ${price} (ID: {order_id})")
                    
                    try:
                        cancel_result = exchange.cancel(symbol, order_id)
                        
                        # Check if the cancellation was actually successful
                        is_successful = False
                        error_message = None
                        
                        if cancel_result and cancel_result.get("status") == "ok":
                            # Check the actual cancellation status in the response
                            response_data = cancel_result.get("response", {})
                            if response_data.get("type") == "cancel":
                                statuses = response_data.get("data", {}).get("statuses", [])
                                
                                for status in statuses:
                                    if status == "success":
                                        is_successful = True
                                        break
                                    elif isinstance(status, dict) and "error" in status:
                                        error_message = status["error"]
                                        break
                                    elif status != "success":
                                        error_message = str(status)
                                        break
                        
                        # Store the REAL Hyperliquid response with correct success/error
                        cancel_response_data = {
                            "status": "success" if is_successful else "error",
                            "message": f"Cancel order response for {symbol} order {order_id}",
                            "operation": "cancel_order",
                            "environment": hyperliquid_config.environment,
                            "timestamp": get_brazil_time().isoformat(),
                            "order_details": {
                                "symbol": symbol,
                                "order_id": order_id,
                                "side": side,
                                "size": size,
                                "price": price
                            },
                            "hyperliquid_response": cancel_result,  # REAL response from Hyperliquid
                            "error": error_message if error_message else None
                        }
                        
                        cancel_hl_response = HyperliquidResponse(
                            webhook_id=webhook_id,
                            response_data=cancel_response_data
                        )
                        await db.hyperliquid_responses.insert_one(cancel_hl_response.dict())
                        
                        if is_successful:
                            await log_message("INFO", f"✅ Order canceled: {order_id}")
                        else:
                            await log_message("ERROR", f"❌ Failed to cancel order {order_id}: {error_message or 'Unknown error'}")
                            
                    except Exception as e:
                        await log_message("ERROR", f"❌ Exception canceling order {order_id}: {str(e)}")
                        
                        # Store the error response
                        error_response_data = {
                            "status": "error",
                            "message": f"Exception canceling order {order_id}",
                            "operation": "cancel_order",
                            "environment": hyperliquid_config.environment,
                            "timestamp": get_brazil_time().isoformat(),
                            "error": str(e),
                            "order_details": {
                                "symbol": symbol,
                                "order_id": order_id,
                                "side": side,
                                "size": size,
                                "price": price
                            }
                        }
                        
                        error_hl_response = HyperliquidResponse(
                            webhook_id=webhook_id,
                            response_data=error_response_data
                        )
                        await db.hyperliquid_responses.insert_one(error_hl_response.dict())
            else:
                await log_message("INFO", f"No remaining orders found for {symbol}")
                
                # Store response indicating no orders to cancel
                no_orders_response_data = {
                    "status": "info",
                    "message": f"No remaining orders found for {symbol}",
                    "operation": "cancel_order",
                    "environment": hyperliquid_config.environment,
                    "timestamp": get_brazil_time().isoformat(),
                    "order_details": {
                        "symbol": symbol,
                        "orders_found": 0
                    }
                }
                
                no_orders_hl_response = HyperliquidResponse(
                    webhook_id=webhook_id,
                    response_data=no_orders_response_data
                )
                await db.hyperliquid_responses.insert_one(no_orders_hl_response.dict())
                
        except Exception as e:
            await log_message("ERROR", f"Error checking/canceling orders for {symbol}: {str(e)}")
            
            # Store error response
            error_response_data = {
                "status": "error",
                "message": f"Error checking orders for {symbol}",
                "operation": "cancel_order",
                "environment": hyperliquid_config.environment,
                "timestamp": get_brazil_time().isoformat(),
                "error": str(e),
                "symbol": symbol
            }
            
            error_hl_response = HyperliquidResponse(
                webhook_id=webhook_id,
                response_data=error_response_data
            )
            await db.hyperliquid_responses.insert_one(error_hl_response.dict())
        
        return True
        
    except Exception as e:
        await log_message("ERROR", f"Error clearing symbol {symbol}: {str(e)}")
        return False

async def close_existing_positions(symbol: str, webhook_id: str):
    """Close all existing positions for a symbol"""
    try:
        positions = await get_open_positions_internal(symbol)
        
        if not positions:
            await log_message("INFO", f"No positions to close for {symbol}")
            return True
        
        exchange = hyperliquid_config.get_exchange_client()
        
        for position in positions:
            size = position['size']
            entry_px = position['entry_px']
            
            # Determine the side to close the position
            # If position size is positive (long), we need to sell to close
            # If position size is negative (short), we need to buy to close
            is_buy = size < 0  # Buy to close short, sell to close long
            close_quantity = abs(size)
            
            await log_message("INFO", f"🔄 Closing position: {size} {symbol} ({'BUY' if is_buy else 'SELL'} {close_quantity})")
            
            # Close position with market order (using limit with IOC) and reduce_only=True
            # Use a price that's close to market but likely to fill immediately
            # Convert entry_px to float to avoid type errors
            # Handle different possible formats: string, float, or None
            entry_px_raw = position['entry_px']
            try:
                if entry_px_raw is None:
                    entry_price = 160.0
                elif isinstance(entry_px_raw, str):
                    entry_price = float(entry_px_raw)
                elif isinstance(entry_px_raw, (int, float)):
                    entry_price = float(entry_px_raw)
                else:
                    # If it's some other type, try to convert to string first then float
                    entry_price = float(str(entry_px_raw))
            except (ValueError, TypeError) as e:
                entry_price = 160.0
                await log_message("WARNING", f"Invalid entry_px for {symbol}: {entry_px_raw} (type: {type(entry_px_raw)}), using default 160.0. Error: {e}")
            
            await log_message("INFO", f"Entry price converted: {entry_px_raw} -> {entry_price}")
            
            if is_buy:
                # For buying (closing short), use a slightly higher price than entry
                close_price = entry_price * 1.1  # 10% above entry price
            else:
                # For selling (closing long), use a slightly lower price than entry
                close_price = entry_price * 0.9  # 10% below entry price
            
            # Ensure price is properly formatted
            close_price = round(close_price, 2)
            
            await log_message("INFO", f"Close order: {symbol} {'BUY' if is_buy else 'SELL'} {close_quantity} @ ${close_price}")
            
            close_result = exchange.order(
                name=symbol,
                is_buy=is_buy,
                sz=close_quantity,
                limit_px=close_price,
                order_type={"limit": {"tif": "Ioc"}},  # Immediate or Cancel (acts like market order)
                reduce_only=True  # This ensures we only close existing positions
            )
            
            # Create response data for the close operation
            if close_result and close_result.get("status") == "ok":
                await log_message("INFO", f"✅ Position closed successfully for {symbol}")
                await log_message("INFO", f"Close result: {close_result}")
                
                # Store the close response in the database
                close_response_data = {
                    "status": "success",
                    "message": f"Position closed successfully for {symbol}",
                    "operation": "close_position",
                    "environment": hyperliquid_config.environment,
                    "timestamp": get_brazil_time().isoformat(),
                    "close_details": {
                        "symbol": symbol,
                        "side": "buy" if is_buy else "sell",
                        "quantity": close_quantity,
                        "price": close_price,
                        "original_position_size": size,
                        "entry_price": entry_price,
                        "hyperliquid_response": close_result
                    }
                }
                
                # Store close response
                close_hl_response = HyperliquidResponse(
                    webhook_id=webhook_id,
                    response_data=close_response_data
                )
                await db.hyperliquid_responses.insert_one(close_hl_response.dict())
                
            else:
                await log_message("ERROR", f"❌ Failed to close position for {symbol}: {close_result}")
                
                # Store the failed close response
                error_response_data = {
                    "status": "error",
                    "message": f"Failed to close position for {symbol}",
                    "operation": "close_position",
                    "environment": hyperliquid_config.environment,
                    "timestamp": get_brazil_time().isoformat(),
                    "close_details": {
                        "symbol": symbol,
                        "side": "buy" if is_buy else "sell",
                        "quantity": close_quantity,
                        "price": close_price,
                        "original_position_size": size,
                        "entry_price": entry_price
                    },
                    "error": str(close_result),
                    "hyperliquid_response": close_result
                }
                
                # Store error response
                error_hl_response = HyperliquidResponse(
                    webhook_id=webhook_id,
                    response_data=error_response_data
                )
                await db.hyperliquid_responses.insert_one(error_hl_response.dict())
                
                return False
        
        return True
        
    except Exception as e:
        await log_message("ERROR", f"Error closing positions for {symbol}: {str(e)}")
        
        # Store the exception response
        exception_response_data = {
            "status": "error",
            "message": f"Exception while closing positions for {symbol}",
            "operation": "close_position",
            "environment": hyperliquid_config.environment,
            "timestamp": get_brazil_time().isoformat(),
            "error": str(e),
            "symbol": symbol
        }
        
        # Store exception response
        exception_hl_response = HyperliquidResponse(
            webhook_id=webhook_id,
            response_data=exception_response_data
        )
        await db.hyperliquid_responses.insert_one(exception_hl_response.dict())
        
        return False

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
        
        # Parse take profit levels
        tp1_price = float(payload.get("tp1_price", 0)) if payload.get("tp1_price") else None
        tp1_perc = float(payload.get("tp1_perc", 0)) if payload.get("tp1_perc") else None
        tp2_price = float(payload.get("tp2_price", 0)) if payload.get("tp2_price") else None
        tp2_perc = float(payload.get("tp2_perc", 0)) if payload.get("tp2_perc") else None
        
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
        
        await log_message("INFO", f"✅ Validation passed - Processing {entry_type} {side} order")
        
        # STEP 1: Clear all orders and positions for this symbol
        await log_message("INFO", f"🧹 Clearing all orders and positions for {symbol}")
        clear_success = await clear_symbol_orders_and_positions(symbol, webhook_id)
        
        if not clear_success:
            await log_message("WARNING", f"⚠️ Failed to clear some orders/positions for {symbol}, continuing with new order")
        else:
            await log_message("INFO", f"✅ Successfully cleared all orders and positions for {symbol}")
        
        # Wait for clearing to complete before opening new position
        await asyncio.sleep(2)  # Give time for positions to close completely
        
        # STEP 2: Execute the new order
        await log_message("INFO", f"🚀 Executing new {entry_type} {side} order")
        
        # Get exchange client
        exchange = hyperliquid_config.get_exchange_client()
        
        # Execute the order using the appropriate method based on entry type
        order_executed = False
        last_error = None
        main_order_result = None
        attempt = 0  # Initialize attempt counter
        
        if entry_type == "market":
            await log_message("INFO", f"🎯 Executing TRUE MARKET order: {side} {quantity} {symbol}")
            
            # Use the dedicated market_open method for true market execution
            try:
                attempt = 1  # Market orders are single attempt
                result = exchange.market_open(
                    name=symbol,  # Use 'name' parameter not 'coin'
                    is_buy=is_buy,
                    sz=quantity,
                    px=None,  # Let it use current market price
                    slippage=0.05,  # 5% slippage tolerance
                    cloid=None
                )
                
                # Check if order was successful
                if result and result.get("status") == "ok":
                    statuses = result.get("response", {}).get("data", {}).get("statuses", [])
                    if statuses and not any("error" in status for status in statuses):
                        await log_message("INFO", f"✅ Market order executed successfully using market_open")
                        order_executed = True
                        main_order_result = result
                    else:
                        error_msg = statuses[0].get("error", "Unknown error") if statuses else "Unknown error"
                        await log_message("ERROR", f"Market order failed: {error_msg}")
                        last_error = error_msg
                else:
                    await log_message("ERROR", f"Market order failed: {result}")
                    last_error = "Market order failed"
                    
            except Exception as market_error:
                await log_message("ERROR", f"Exception in market_open: {str(market_error)}")
                last_error = str(market_error)
                
        else:  # limit orders
            await log_message("INFO", f"🎯 Executing LIMIT order: {side} {quantity} {symbol} @ ${price}")
            
            # For limit orders, use the traditional exchange.order method with retry logic
            for attempt in range(5):  # Try up to 5 different price formats
                try:
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
                            await log_message("INFO", f"✅ Limit order executed successfully on attempt {attempt + 1}")
                            order_executed = True
                            main_order_result = result
                            break
                        else:
                            error_msg = statuses[0].get("error", "Unknown error") if statuses else "Unknown error"
                            await log_message("WARNING", f"Limit order attempt {attempt + 1} failed: {error_msg}")
                            last_error = error_msg
                            continue
                    
                except Exception as order_error:
                    await log_message("WARNING", f"Limit order attempt {attempt + 1} exception: {str(order_error)}")
                    last_error = str(order_error)
                    continue
        
        if order_executed:
            await log_message("INFO", f"✅ Hyperliquid order executed successfully after {attempt} attempts!")
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
                    "attempts": attempt,
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

@api_router.get("/orders/history")
async def get_orders_history(limit: int = 20):
    """Get recent orders history from Hyperliquid"""
    try:
        # Get wallet address
        wallet_address = await get_wallet_address()
        if not wallet_address:
            raise HTTPException(status_code=500, detail="No wallet address found")
        
        # Get info client
        info = hyperliquid_config.get_info_client()
        
        # Get user fills (order history) 
        user_fills = info.user_fills(wallet_address)
        
        # Get recent orders (last 20 by default)
        recent_orders = user_fills[-limit:] if len(user_fills) > limit else user_fills
        
        # Format orders for display
        formatted_orders = []
        for order in recent_orders:
            formatted_order = {
                "time": order.get("time", ""),
                "coin": order.get("coin", ""),
                "side": order.get("side", ""),
                "sz": order.get("sz", ""),
                "px": order.get("px", ""),
                "fee": order.get("fee", ""),
                "order_id": order.get("oid", ""),
                "order_type": order.get("orderType", "Unknown"),  # This will show if it's Market or Limit
                "liquidation": order.get("liquidation", False),
                "dir": order.get("dir", ""),
                "hash": order.get("hash", ""),
                "crossed": order.get("crossed", False),
                "start_position": order.get("startPosition", ""),
                "closed_pnl": order.get("closedPnl", "")
            }
            formatted_orders.append(formatted_order)
        
        await log_message("INFO", f"📊 Retrieved {len(formatted_orders)} recent orders from Hyperliquid")
        
        return {
            "status": "success",
            "wallet_address": wallet_address,
            "total_orders": len(formatted_orders),
            "orders": formatted_orders
        }
        
    except Exception as e:
        await log_message("ERROR", f"Failed to get orders history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/orders/open")
async def get_open_orders():
    """Get current open orders from Hyperliquid"""
    try:
        # Get wallet address
        wallet_address = await get_wallet_address()
        if not wallet_address:
            raise HTTPException(status_code=500, detail="No wallet address found")
        
        # Get info client
        info = hyperliquid_config.get_info_client()
        
        # Get open orders
        open_orders = info.open_orders(wallet_address)
        
        # Format orders for display
        formatted_orders = []
        for order in open_orders:
            formatted_order = {
                "coin": order.get("coin", ""),
                "side": order.get("side", ""),
                "sz": order.get("sz", ""),
                "limit_px": order.get("limitPx", ""),
                "order_id": order.get("oid", ""),
                "timestamp": order.get("timestamp", ""),
                "order_type": order.get("orderType", "Unknown"),  # This will show if it's Market or Limit
                "trigger_condition": order.get("triggerCondition", ""),
                "trigger_px": order.get("triggerPx", ""),
                "is_positional": order.get("isPositional", False),
                "reduce_only": order.get("reduceOnly", False),
                "original_sz": order.get("origSz", ""),
                "cloid": order.get("cloid", "")
            }
            formatted_orders.append(formatted_order)
        
        await log_message("INFO", f"📊 Retrieved {len(formatted_orders)} open orders from Hyperliquid")
        
        return {
            "status": "success",
            "wallet_address": wallet_address,
            "total_orders": len(formatted_orders),
            "orders": formatted_orders
        }
        
    except Exception as e:
        await log_message("ERROR", f"Failed to get open orders: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
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
            timestamp=get_brazil_time().isoformat(),
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
        # Use _id for sorting to ensure proper chronological order
        # _id contains timestamp information and is always in chronological order
        webhooks = await db.webhooks.find().sort("_id", -1).limit(limit).to_list(limit)
        
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
            "timestamp": get_brazil_time().isoformat(),
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
        # Use _id for sorting to ensure proper chronological order
        responses = await db.hyperliquid_responses.find().sort("_id", -1).limit(limit).to_list(limit)
        
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

@api_router.delete("/logs")
async def clear_logs():
    """Clear all logs from the database"""
    try:
        result = await db.logs.delete_many({})
        
        await log_message("INFO", f"Logs cleared via API - {result.deleted_count} logs deleted")
        
        return {
            "status": "success", 
            "message": f"Successfully cleared {result.deleted_count} logs",
            "deleted_count": result.deleted_count
        }
        
    except Exception as e:
        await log_message("ERROR", f"Failed to clear logs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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