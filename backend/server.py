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
from datetime import datetime, timedelta
import pytz
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants
import json
import asyncio
import time
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
    strategy_id: Optional[str] = "OTHERS"  # Strategy segmentation

class HyperliquidResponse(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: get_brazil_time().isoformat())
    webhook_id: str
    response_data: Dict[str, Any]
    status: str = "sent"
    error: Optional[str] = None
    strategy_id: Optional[str] = "OTHERS"  # Strategy segmentation

class StrategyRule(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    strategy_id: str
    rule_name: str
    rule_config: Dict[str, Any] = {}
    enabled: bool = True
    created_at: str = Field(default_factory=lambda: get_brazil_time().isoformat())
    updated_at: str = Field(default_factory=lambda: get_brazil_time().isoformat())

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

# Strategy Management System
class StrategyManager:
    def __init__(self):
        self.strategies = {}
        self.default_strategies = {
            "IMBA_HYPER": {
                "name": "IMBA Hyper Strategy",
                "enabled": True,
                "rules": {
                    "max_position_size": 100.0,
                    "stop_loss_enabled": True,
                    "take_profit_enabled": True,
                    "position_clearing_method": "market_close",
                    "risk_management": {
                        "max_daily_trades": 50,
                        "max_drawdown": 0.05
                    }
                }
            },
            "IMBA_TREND": {
                "name": "IMBA Trend Strategy",
                "enabled": True,
                "rules": {
                    "max_position_size": 75.0,
                    "stop_loss_enabled": True,
                    "take_profit_enabled": True,
                    "single_tp_only": True,  # Apenas 1 TP
                    "use_sl_price": True,    # Usar sl_price em vez de stop
                    "position_clearing_method": "market_close",
                    "risk_management": {
                        "max_daily_trades": 30,
                        "max_drawdown": 0.04
                    }
                }
            },
            "OTHERS": {
                "name": "Other Strategies",
                "enabled": True,
                "rules": {
                    "max_position_size": 50.0,
                    "stop_loss_enabled": True,
                    "take_profit_enabled": True,
                    "position_clearing_method": "market_close",
                    "risk_management": {
                        "max_daily_trades": 25,
                        "max_drawdown": 0.03
                    }
                }
            }
        }
        self.load_strategies()
    
    def load_strategies(self):
        """Load strategies from database or use defaults"""
        self.strategies = self.default_strategies.copy()
    
    def get_strategy(self, strategy_id: str) -> Dict[str, Any]:
        """Get strategy configuration"""
        return self.strategies.get(strategy_id, self.strategies["OTHERS"])
    
    def add_strategy(self, strategy_id: str, config: Dict[str, Any] = None):
        """Add new strategy automatically"""
        if strategy_id not in self.strategies:
            self.strategies[strategy_id] = {
                "name": f"Strategy {strategy_id}",
                "enabled": True,
                "rules": config or self.default_strategies["OTHERS"]["rules"].copy()
            }
            asyncio.create_task(self.log_new_strategy(strategy_id))
    
    async def log_new_strategy(self, strategy_id: str):
        """Log when a new strategy is discovered"""
        await log_message("INFO", f"🔄 Nova estratégia descoberta automaticamente: {strategy_id}")
    
    def get_all_strategy_ids(self) -> List[str]:
        """Get all known strategy IDs, excluding test strategies"""
        excluded_strategies = ['TEST_STRATEGY_1755553991', 'TEST_STRATEGY_1755552323']
        return [sid for sid in self.strategies.keys() if sid not in excluded_strategies]
    
    def is_strategy_enabled(self, strategy_id: str) -> bool:
        """Check if strategy is enabled"""
        strategy = self.get_strategy(strategy_id)
        return strategy.get("enabled", True)

# Global strategy manager instance
strategy_manager = StrategyManager()

# Stats tracking
stats = defaultdict(int)
stats['total_webhooks'] = 0
stats['successful_forwards'] = 0
stats['failed_forwards'] = 0

# Uptime monitoring (persistent in database)
uptime_stats = {
    'total_pings': 0,
    'successful_pings': 0,
    'start_time': time.time(),
    'last_reset_time': time.time(),
    'monitoring_start_time': get_brazil_time(),  # Store when monitoring started (persistent)
    'was_reset': False  # Flag to track if reset was used
}
uptime_task = None

server_start_time = get_brazil_time()

# Utility functions

async def load_persistent_uptime_stats():
    """Load uptime statistics from database (survives container restarts)"""
    try:
        # Try to get existing uptime document
        existing_stats = await db.uptime_persistent.find_one({"_id": "global_uptime"})
        
        if existing_stats:
            # Load persistent data
            uptime_stats['total_pings'] = existing_stats.get('total_pings', 0)
            uptime_stats['successful_pings'] = existing_stats.get('successful_pings', 0)
            uptime_stats['monitoring_start_time'] = existing_stats.get('monitoring_start_time')
            
            # Reset session counters but keep total/monitoring_start_time
            uptime_stats['start_time'] = time.time()
            uptime_stats['was_reset'] = False
            
            await log_message("INFO", f"📊 Loaded persistent uptime: {uptime_stats['successful_pings']}/{uptime_stats['total_pings']} pings since {uptime_stats['monitoring_start_time']}")
        else:
            # First time ever - create new persistent record
            uptime_stats['total_pings'] = 0
            uptime_stats['successful_pings'] = 0
            uptime_stats['monitoring_start_time'] = None  # Will be set on first successful ping
            uptime_stats['start_time'] = time.time()
            uptime_stats['was_reset'] = False
            
            await save_persistent_uptime_stats()
            await log_message("INFO", "📊 Initialized new persistent uptime monitoring")
            
    except Exception as e:
        await log_message("ERROR", f"❌ Error loading persistent uptime stats: {str(e)}")
        # Reset to defaults if error
        uptime_stats['total_pings'] = 0
        uptime_stats['successful_pings'] = 0
        uptime_stats['monitoring_start_time'] = None
        uptime_stats['start_time'] = time.time()
        uptime_stats['was_reset'] = False

async def save_persistent_uptime_stats():
    """Save uptime statistics to database (persistent across restarts)"""
    try:
        stats_doc = {
            "_id": "global_uptime",
            "total_pings": uptime_stats['total_pings'],
            "successful_pings": uptime_stats['successful_pings'],
            "monitoring_start_time": uptime_stats['monitoring_start_time'],
            "last_updated": get_brazil_time().strftime('%Y-%m-%d %H:%M:%S'),
            "last_server_start": server_start_time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        await db.uptime_persistent.replace_one(
            {"_id": "global_uptime"}, 
            stats_doc, 
            upsert=True
        )
    except Exception as e:
        await log_message("ERROR", f"❌ Error saving persistent uptime stats: {str(e)}")

async def ping_uptime_monitor():
    """
    Background task that pings a reliable server every 5 seconds to monitor uptime.
    Only logs errors, not successful pings.
    """
    while True:
        try:
            ping_successful = False
            
            # Try ping first, fallback to wget if ping fails
            try:
                # Ping Cloudflare DNS (1.1.1.1) with 2 second timeout
                process = await asyncio.create_subprocess_exec(
                    'ping', '-c', '1', '-W', '2', '1.1.1.1',
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
                
                # Wait for ping to complete with timeout
                await asyncio.wait_for(process.wait(), timeout=3.0)
                
                if process.returncode == 0:
                    ping_successful = True
                else:
                    # Try alternative method with wget
                    raise Exception(f"Ping failed with return code {process.returncode}")
                    
            except Exception:
                # Fallback to wget/curl for HTTP connectivity test
                try:
                    process = await asyncio.create_subprocess_exec(
                        'wget', '--timeout=2', '--tries=1', '-q', '--spider', 'http://1.1.1.1',
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL
                    )
                    
                    await asyncio.wait_for(process.wait(), timeout=3.0)
                    
                    if process.returncode == 0:
                        ping_successful = True
                except Exception:
                    pass  # ping_successful remains False
            
            # Update counters
            uptime_stats['total_pings'] += 1
            
            if ping_successful:
                uptime_stats['successful_pings'] += 1
                
                # Set monitoring start time on first successful ping (clean format)
                if uptime_stats['monitoring_start_time'] is None:
                    # Store in clean format without decimals
                    start_time = get_brazil_time()
                    uptime_stats['monitoring_start_time'] = start_time.strftime('%Y-%m-%d %H:%M:%S')
                    await log_message("INFO", f"📊 First successful ping - monitoring started at {uptime_stats['monitoring_start_time']}")
            else:
                # Only log errors
                await log_message("ERROR", f"❌ Uptime check failed: ping and wget both failed")
            
            # Save to database every 10 pings (persistent)
            if uptime_stats['total_pings'] % 10 == 0:
                await save_persistent_uptime_stats()
                
        except asyncio.TimeoutError:
            uptime_stats['total_pings'] += 1
            await log_message("ERROR", "❌ Uptime check timeout")
        except Exception as e:
            uptime_stats['total_pings'] += 1
            await log_message("ERROR", f"❌ Uptime check error: {str(e)}")
        
        # Wait 5 seconds before next ping
        await asyncio.sleep(5)

def get_uptime_percentage():
    """Calculate uptime percentage (current session only)"""
    if uptime_stats['total_pings'] == 0:
        return 100.0  # No pings yet, assume 100%
    
    return (uptime_stats['successful_pings'] / uptime_stats['total_pings']) * 100

def reset_uptime_stats():
    """Reset uptime statistics (counter starts from zero)"""
    uptime_stats['total_pings'] = 0
    uptime_stats['successful_pings'] = 0
    uptime_stats['monitoring_start_time'] = None  # Will be set on next successful ping
    uptime_stats['was_reset'] = True

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
                # Check specifically for rate limit
                error_str = str(e)
                if "429" in error_str:
                    await log_message("ERROR", f"❌ Rate limit detected for {address}: {error_str}")
                    # Return cached data if available to avoid further rate limiting
                    if balance_cache["balance"] is not None:
                        await log_message("INFO", f"🔄 Using cached data due to rate limit: ${balance_cache['balance']}")
                        return balance_cache["address"], balance_cache["balance"]
                    # If no cache, wait a bit and continue
                    await asyncio.sleep(2)
                else:
                    await log_message("WARNING", f"Error checking address {address}: {str(e)}")
                continue
        
        await log_message("WARNING", "No account with balance found in discovered accounts")
        return None, 0.0
        
    except Exception as e:
        error_str = str(e)
        if "429" in error_str:
            await log_message("ERROR", f"❌ Rate limit in find_account_with_balance: {error_str}")
            # Return cached data if available
            if balance_cache["balance"] is not None:
                await log_message("INFO", f"🔄 Using cached data due to rate limit: ${balance_cache['balance']}")
                return balance_cache["address"], balance_cache["balance"]
        else:
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
        error_str = str(e)
        if "429" in error_str:
            await log_message("ERROR", f"❌ Rate limit in get_cached_balance, extending cache time")
            # Extend cache time to 15 minutes when rate limited
            balance_cache["expires_in"] = 900  # 15 minutes
        else:
            await log_message("ERROR", f"Error fetching balance: {str(e)}")
        
        # Return cached data if available, even if expired
        if balance_cache["balance"] is not None:
            await log_message("INFO", f"Returning stale cache due to error: ${balance_cache['balance']}")
            return balance_cache["address"], balance_cache["balance"]
        return None, None

async def get_account_balance():
    """Get Hyperliquid exchange account balance with caching"""
    try:
        result = await get_cached_balance()
        if isinstance(result, tuple) and len(result) == 2:
            address, balance = result
            return balance
        else:
            return result
                
    except Exception as e:
        await log_message("ERROR", f"Failed to get account balance: {str(e)}")
        return None

async def get_wallet_address():
    """Get the correct wallet address with caching"""
    try:
        result = await get_cached_balance()
        if isinstance(result, tuple) and len(result) == 2:
            address, balance = result
            return address
        else:
            return None
        
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
        
        # Extract strategy_id from payload
        strategy_id = payload.get("strategy_id", "OTHERS")
        
        # Auto-register new strategies
        strategy_manager.add_strategy(strategy_id)
        
        # Log successful webhook processing with strategy info
        await log_message("INFO", "✅ WEBHOOK VALIDATION SUCCESS")
        await log_message("INFO", f"Strategy ID: {strategy_id}")
        await log_message("INFO", f"Final Payload: {payload}")
        
        # Log the incoming webhook with strategy_id
        webhook_msg = WebhookMessage(payload=payload, strategy_id=strategy_id)
        await db.webhooks.insert_one(webhook_msg.dict())
        stats['total_webhooks'] += 1
        
        await log_message("INFO", f"✅ WEBHOOK STORED: {webhook_msg.id} [Strategy: {strategy_id}]")
        
        # Forward to Hyperliquid
        try:
            await log_message("INFO", "🚀 FORWARDING TO HYPERLIQUID")
            hyperliquid_response = await forward_to_hyperliquid(webhook_msg.id, payload, strategy_id)
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
    """Get asset metadata from Hyperliquid including szDecimals and pxDecimals"""
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
            # Get szDecimals from asset info
            sz_decimals = asset_info.get("szDecimals", 3)
            
            # Manual mapping for pxDecimals since Hyperliquid API doesn't provide it consistently
            px_decimals_map = {
                "ETH": 2,    # ETH prices like 4514.49 (2 decimals)
                "BTC": 1,    # BTC prices like 65432.1 (1 decimal)  
                "SOL": 2,    # SOL prices like 175.45 (2 decimals)
                "AVAX": 2,   # AVAX similar to SOL
                "ATOM": 2,   # ATOM similar precision
                "BNB": 2,    # BNB similar precision
            }
            
            px_decimals = px_decimals_map.get(symbol, 2)  # Default to 2 decimals
            
            await log_message("INFO", f"📏 {symbol} szDecimals: {sz_decimals}, pxDecimals: {px_decimals} (manual mapping)")
            return {"szDecimals": sz_decimals, "pxDecimals": px_decimals}
        
        # Default fallback
        await log_message("WARNING", f"⚠️ Asset {symbol} not found in metadata, using default szDecimals: 3, pxDecimals: 2")
        return {"szDecimals": 3, "pxDecimals": 2}
        
    except Exception as e:
        await log_message("ERROR", f"❌ Error getting asset info for {symbol}: {str(e)}")
        return {"szDecimals": 3, "pxDecimals": 2}  # Default fallback

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

def format_tpsl_price(price: float, symbol: str) -> float:
    """
    Format TP/SL price based on asset-specific requirements
    
    CRITICAL: Based on testing, ETH rejects decimal prices for TP/SL orders
    while other assets like SOL accept them.
    
    Args:
        price: The raw price to format
        symbol: The asset symbol (e.g., 'ETH', 'SOL', 'BTC')
    
    Returns:
        Formatted price (integer for ETH, decimal for others)
    """
    # Assets that require INTEGER prices for TP/SL (no decimals)
    INTEGER_PRICE_ASSETS = {'ETH', 'BTC'}
    
    if symbol in INTEGER_PRICE_ASSETS:
        # Round to nearest integer for ETH/BTC
        formatted_price = float(int(round(price)))
        return formatted_price
    else:
        # For other assets (SOL, AVAX, etc.), use 2 decimal places
        formatted_price = round(price, 2)
        return formatted_price

def check_order_response_for_errors(response: dict) -> tuple[bool, str]:
    """
    Check Hyperliquid order response for errors
    
    IMPORTANT: Hyperliquid returns status="ok" even when orders fail.
    The actual error is inside response.data.statuses[]
    
    Args:
        response: The response from Hyperliquid API
    
    Returns:
        Tuple of (success: bool, error_message: str)
    """
    if not response:
        return False, "No response received"
    
    # Check top-level status
    if response.get("status") != "ok":
        return False, str(response.get("error", "Unknown error"))
    
    # Check inside statuses for actual errors
    response_data = response.get("response", {})
    if response_data.get("type") == "order":
        statuses = response_data.get("data", {}).get("statuses", [])
        
        for status in statuses:
            if isinstance(status, dict):
                # Check for error field
                if "error" in status:
                    return False, status["error"]
                # Check for filled or resting (success)
                if "filled" in status or "resting" in status:
                    return True, ""
        
        # If we have statuses but no error and no success indicator
        if statuses:
            return True, ""
    
    # Default to success if status is "ok"
    return True, ""

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
            return False
        
        await log_message("INFO", f"🧹 Clearing all orders and positions for {symbol}")
        
        # Track overall success
        overall_success = True
        
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
                            
                            await log_message("INFO", f"🔄 Closing position: {size} {symbol} using market_close method")
                            
                            try:
                                # Use exchange.market_close() method for proper position closing
                                # This method is specifically designed for closing positions
                                await log_message("INFO", f"🎯 Using exchange.market_close() to close position: {size} {symbol}")
                                
                                # Add detailed logging for debugging
                                await log_message("INFO", f"   Parameters: coin={symbol}, sz={close_quantity}, px=None, slippage=0.05")
                                
                                try:
                                    close_result = exchange.market_close(
                                        coin=symbol,  # Use 'coin' parameter for market_close
                                        sz=close_quantity,  # Size to close (absolute value)
                                        px=None,  # Let it use current market price
                                        slippage=0.05  # 5% slippage tolerance
                                    )
                                    
                                    await log_message("INFO", f"   market_close() completed, result type: {type(close_result)}")
                                    await log_message("INFO", f"   market_close() raw result: {close_result}")
                                    
                                    # Check for None response (API returning null)
                                    if close_result is None:
                                        await log_message("WARNING", f"❌ market_close() returned None - triggering fallback mechanism")
                                        raise Exception("market_close() returned None response - fallback needed")
                                    
                                except Exception as close_error:
                                    await log_message("ERROR", f"❌ Exception in exchange.market_close(): {str(close_error)}")
                                    await log_message("ERROR", f"   Exception type: {type(close_error).__name__}")
                                    await log_message("ERROR", f"   Exception details: {repr(close_error)}")
                                    
                                    # FALLBACK MECHANISM: Try with different parameters first
                                    try:
                                        await log_message("INFO", f"🔄 Retrying market_close with minimal parameters...")
                                        close_result = exchange.market_close(coin=symbol)
                                        
                                        if close_result is not None:
                                            await log_message("INFO", f"   Minimal parameter result: {close_result}")
                                        else:
                                            await log_message("WARNING", f"   Minimal parameter attempt also returned None")
                                            raise Exception("Minimal parameter market_close also returned None")
                                            
                                    except Exception as minimal_error:
                                        await log_message("ERROR", f"❌ Minimal parameter attempt also failed: {str(minimal_error)}")
                                        
                                        # FINAL FALLBACK: Use market_open method for closing positions
                                        await log_message("WARNING", f"🔄 Falling back to market_open method for closing...")
                                        
                                        # Use market_open with appropriate side for closing the position
                                        # If size < 0 (short), we need to BUY to close
                                        # If size > 0 (long), we need to SELL to close
                                        is_buy_to_close = size < 0
                                        
                                        close_result = exchange.market_open(
                                            name=symbol,
                                            is_buy=is_buy_to_close,
                                            sz=close_quantity,
                                            px=None,  # Use market price
                                            slippage=0.05,  # 5% slippage
                                            cloid=None
                                        )
                                        
                                        await log_message("INFO", f"   Fallback market_open result: {close_result}")
                                        
                                        # Don't re-raise - let the fallback result be processed
                                        # Update method tracking
                                        method_used = "market_open_fallback"
                                
                                # Check if the close was actually successful
                                is_successful = False
                                error_message = None
                                method_used = "market_close"  # Track which method was used
                                
                                # Handle None response
                                if close_result is None:
                                    error_message = "market_close() returned None response"
                                    await log_message("ERROR", f"❌ market_close() returned None response")
                                elif close_result and close_result.get("status") == "ok":
                                    # Check the actual order status in the response
                                    response_data = close_result.get("response", {})
                                    if response_data.get("type") == "order":
                                        statuses = response_data.get("data", {}).get("statuses", [])
                                        
                                        # For market_close, check for successful execution
                                        if statuses:
                                            for status in statuses:
                                                if isinstance(status, dict) and "error" in status:
                                                    error_message = status["error"]
                                                    # Check if this is the old error we fixed
                                                    if "order could not immediately match" in error_message.lower():
                                                        method_used = "reduce_only_fallback"
                                                    break
                                                elif "filled" in str(status).lower() or status == "success":
                                                    is_successful = True
                                                    break
                                            
                                            # If no explicit error found and we have a status, consider it successful
                                            if not error_message and not is_successful and statuses:
                                                # Check if the first status doesn't contain error
                                                first_status = statuses[0]
                                                if isinstance(first_status, dict):
                                                    if "error" not in first_status:
                                                        is_successful = True
                                                else:
                                                    if "error" not in str(first_status).lower():
                                                        is_successful = True
                                        else:
                                            # No statuses but OK response - likely successful
                                            is_successful = True
                                    else:
                                        # Non-order type response but OK status - likely successful
                                        is_successful = True
                                else:
                                    # Extract error message from failed response
                                    if close_result:
                                        error_message = str(close_result.get("error", close_result))
                                        # Check if we're using the fallback method
                                        if "market_open" in str(close_result).lower():
                                            method_used = "market_open_fallback"
                                    else:
                                        error_message = "Unknown error - no response received"
                                
                                # Store the REAL Hyperliquid response with correct success/error
                                close_response_data = {
                                    "status": "success" if is_successful else "error",
                                    "message": f"Position close response for {symbol}",
                                    "operation": "close_position",
                                    "environment": hyperliquid_config.environment,
                                    "timestamp": get_brazil_time().isoformat(),
                                    "position_details": {
                                        "symbol": symbol,
                                        "original_size": size,
                                        "close_quantity": close_quantity,
                                        "close_method": method_used,  # Track actual method used (market_close, market_open_fallback, etc)
                                        "direction": "closing_short" if size < 0 else "closing_long",
                                        "fallback_used": "fallback" in method_used
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
                                    await log_message("INFO", f"✅ Position closed successfully: {size} {symbol}")
                                else:
                                    await log_message("ERROR", f"❌ Failed to close position {size} {symbol}: {error_message or 'Unknown error'}")
                                    overall_success = False  # Mark as failed
                                    
                            except Exception as e:
                                await log_message("ERROR", f"❌ Exception closing position {size} {symbol}: {str(e)}")
                                overall_success = False  # Mark as failed
                                
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
                                        "close_method": method_used,
                                        "fallback_used": "fallback" in method_used
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
            overall_success = False  # Mark as failed
            
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
                            # Don't mark overall_success as False for order cancellation failures
                            
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
        
        return overall_success
        
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

def truncate_to_decimals(value: float, decimals: int) -> float:
    """
    Truncate a float to a specific number of decimal places (not round).
    This ensures the value never exceeds the original value.
    """
    multiplier = 10 ** decimals
    return int(value * multiplier) / multiplier


def format_price_for_symbol(price: float, symbol: str) -> float:
    """
    Format price to be compatible with the exchange's tick size requirements.
    Only truncates if the price has more precision than the tick size allows.
    """
    if symbol in ["SOL", "ETH", "AVAX"]:
        # Tick size 0.50 - format to nearest 0.50 (truncate excess precision)
        return int(price * 2) / 2
    elif symbol in ["BTC"]:
        # Tick size 10 - format to nearest 10 (truncate excess precision)
        return int(price / 10) * 10
    else:
        # Default tick size 0.0001 - format to 4 decimal places
        return truncate_to_decimals(price, 4)

def format_price_with_px_decimals(price: float, px_decimals: int) -> float:
    """
    Format price using pxDecimals for precise price formatting.
    Truncates (not rounds) to maintain exact precision from webhook signal.
    """
    return truncate_to_decimals(price, px_decimals)

async def forward_to_hyperliquid(webhook_id: str, payload: Dict[str, Any], strategy_id: str = "OTHERS"):
    """Forward the webhook payload to Hyperliquid and execute real trades"""
    try:
        await log_message("INFO", f"🚀 Processing TradingView webhook {webhook_id} [Strategy: {strategy_id}]")
        await log_message("INFO", f"📊 Payload received: {payload}")
        
        # Get strategy configuration
        strategy_config = strategy_manager.get_strategy(strategy_id)
        
        # Check if strategy is enabled
        if not strategy_manager.is_strategy_enabled(strategy_id):
            await log_message("WARNING", f"🚫 Strategy {strategy_id} is disabled, skipping execution")
            return {
                "status": "skipped",
                "message": f"Strategy {strategy_id} is disabled",
                "strategy_id": strategy_id
            }
        
        await log_message("INFO", f"⚙️ Using strategy configuration: {strategy_config['name']}")
        
        # Parse the TradingView payload - NEW FORMAT
        symbol = payload.get("symbol", "").upper()  # SOL, BTC, ETH, etc.
        side = payload.get("side", "").lower()  # buy/sell
        entry_type = payload.get("entry", "market").lower()  # market/limit
        raw_quantity = float(payload.get("quantity", 0))
        raw_price = float(payload.get("price", 0)) if payload.get("price") else None  # Price for limit orders
        # Stop price será definido na seção de estratégia específica
        
        # Apply strategy-specific rules
        strategy_rules = strategy_config.get("rules", {})
        max_position_size = strategy_rules.get("max_position_size", 100.0)
        
        # Validate position size against strategy limits
        if raw_quantity > max_position_size:
            await log_message("WARNING", f"⚠️ Position size {raw_quantity} exceeds strategy limit {max_position_size}, adjusting")
            raw_quantity = max_position_size
        
        # Parse take profit levels - ESTRATÉGIA ESPECÍFICA
        if strategy_id == "IMBA_TREND":
            # Para IMBA_TREND, usar apenas tp_price como tp1 e sl_price como stop
            raw_tp1_price = float(payload.get("tp_price", 0)) if payload.get("tp_price") else None
            tp1_perc = None  # IMBA_TREND usa preço absoluto, não percentual
            tp2_price = None
            tp2_perc = None
            tp3_price = None
            tp3_perc = None
            tp4_price = None
            tp4_perc = None
            
            # Para IMBA_TREND, usar sl_price se disponível, senão usar stop
            if payload.get("sl_price"):
                raw_stop_price = float(payload.get("sl_price"))
            elif payload.get("stop"):
                raw_stop_price = float(payload.get("stop"))
            else:
                raw_stop_price = None
            
            # IMPORTANTE: Aplicar formatação específica por ativo para IMBA_TREND
            # ETH requer preços inteiros, outros aceitam decimais
            tp1_price = format_tpsl_price(raw_tp1_price, symbol) if raw_tp1_price else None
            stop_price = format_tpsl_price(raw_stop_price, symbol) if raw_stop_price else None
                
            await log_message("INFO", f"📊 IMBA_TREND formatado: tp_price={tp1_price} (orig: {raw_tp1_price}), sl_price={stop_price} (orig: {raw_stop_price}) - formatação específica para {symbol}")
        else:
            # Para IMBA_HYPER e outras estratégias, usar sistema multi-TP original completo
            tp1_price = float(payload.get("tp1_price", 0)) if payload.get("tp1_price") else None
            tp1_perc = float(payload.get("tp1_perc", 0)) if payload.get("tp1_perc") else None
            tp2_price = float(payload.get("tp2_price", 0)) if payload.get("tp2_price") else None
            tp2_perc = float(payload.get("tp2_perc", 0)) if payload.get("tp2_perc") else None
            tp3_price = float(payload.get("tp3_price", 0)) if payload.get("tp3_price") else None
            tp3_perc = float(payload.get("tp3_perc", 0)) if payload.get("tp3_perc") else None
            tp4_price = float(payload.get("tp4_price", 0)) if payload.get("tp4_price") else None
            tp4_perc = float(payload.get("tp4_perc", 0)) if payload.get("tp4_perc") else None
            
            # Para outras estratégias, usar campo "stop" padrão
            stop_price = float(payload.get("stop", 0)) if payload.get("stop") else None
        
        # Get asset information from Hyperliquid
        await log_message("INFO", f"🔍 Getting asset info for {symbol}")
        asset_info = await get_asset_info(symbol)
        sz_decimals = asset_info["szDecimals"]
        px_decimals = asset_info["pxDecimals"]
        
        await log_message("INFO", f"📏 Asset {symbol} - szDecimals: {sz_decimals}, pxDecimals: {px_decimals}")
        
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
        await log_message("INFO", f"  TP1 Price: {tp1_price}, TP1 Percentage: {tp1_perc}")
        await log_message("INFO", f"  TP2 Price: {tp2_price}, TP2 Percentage: {tp2_perc}")
        await log_message("INFO", f"  TP3 Price: {tp3_price}, TP3 Percentage: {tp3_perc}")
        await log_message("INFO", f"  TP4 Price: {tp4_price}, TP4 Percentage: {tp4_perc}")
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
            await log_message("ERROR", f"❌ Failed to clear orders/positions for {symbol}. Aborting order execution.")
            
            # Return error response
            error_response = {
                "status": "error",
                "message": f"Failed to clear existing orders/positions for {symbol}. New order not executed.",
                "environment": hyperliquid_config.environment,
                "timestamp": get_brazil_time().isoformat(),
                "order_details": {
                    "symbol": symbol,
                    "side": side,
                    "entry_type": entry_type,
                    "quantity": quantity,
                    "price": price,
                    "stop_price": stop_price,
                    "tp1_price": tp1_price,
                    "tp1_perc": tp1_perc,
                    "tp2_price": tp2_price,
                    "tp2_perc": tp2_perc,
                    "error": "Failed to clear existing positions"
                },
                "original_payload": payload
            }
            
            # Store the error response
            hl_response = HyperliquidResponse(
                webhook_id=webhook_id,
                response_data=error_response
            )
            await db.hyperliquid_responses.insert_one(hl_response.dict())
            
            return error_response
        else:
            await log_message("INFO", f"✅ Successfully cleared all orders and positions for {symbol}")
        
        # Wait for clearing to complete before opening new position
        await asyncio.sleep(3)  # Give more time for positions to close completely
        
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
                    
                    # Format stop price using asset-specific formatting (ETH=integer, others=decimal)
                    formatted_stop_price = format_tpsl_price(stop_price, symbol)
                    
                    await log_message("INFO", f"🛑 Placing stop loss: {'BUY' if stop_is_buy else 'SELL'} {quantity} {symbol} at ${formatted_stop_price} (original: ${stop_price}, formatted for {symbol})")
                    
                    # TRIGGER ORDER: Stop Loss as conditional trigger order (Market execution)
                    await log_message("INFO", f"🛑 Placing stop loss as TRIGGER ORDER (Market execution when triggered)")
                    
                    stop_order_result = exchange.order(
                        name=symbol,
                        is_buy=stop_is_buy,
                        sz=quantity,
                        limit_px=formatted_stop_price,
                        order_type={
                            "trigger": {
                                "triggerPx": formatted_stop_price,
                                "isMarket": True,  # Market execution when triggered
                                "tpsl": "sl"  # Stop Loss
                            }
                        }
                        # SEM reduce_only=True - essa foi a chave do sucesso anterior
                        # Removido reduce_only=True para ordens trigger com tpsl
                    )
                    
                    # Check for errors in response (status="ok" doesn't guarantee success)
                    is_success, error_msg = check_order_response_for_errors(stop_order_result)
                    
                    if is_success:
                        await log_message("INFO", f"✅ Stop loss order placed successfully!")
                        await log_message("INFO", f"🛑 Stop loss result: {stop_order_result}")
                    else:
                        await log_message("ERROR", f"❌ Failed to place stop loss order: {error_msg}")
                        await log_message("ERROR", f"🛑 Full response: {stop_order_result}")
                    
                except Exception as stop_error:
                    await log_message("ERROR", f"❌ Error placing stop loss order: {str(stop_error)}")
                    stop_order_result = {"error": str(stop_error)}
            
            # Place take profit orders if specified
            tp_order_results = []
            
            # Handle TP1
            if tp1_price or tp1_perc:
                await log_message("INFO", f"🎯 Setting up take profit 1 order - tp1_price: {tp1_price}, tp1_perc: {tp1_perc}")
                try:
                    # Calculate TP1 price
                    if tp1_price:
                        tp1_target = tp1_price
                    else:
                        # Calculate from percentage
                        entry_price = float(main_order_result.get("response", {}).get("data", {}).get("statuses", [{}])[0].get("filled", {}).get("avgPx", 0))
                        if entry_price > 0:
                            if is_buy:
                                tp1_target = entry_price * (1 + tp1_perc / 100)
                            else:
                                tp1_target = entry_price * (1 - tp1_perc / 100)
                        else:
                            raise ValueError("Could not determine entry price for TP percentage calculation")
                    
                    # Use tp1_perc directly as size (it's not a percentage, but the actual size)
                    if tp1_perc:
                        tp1_size = float(tp1_perc)  # Ensure it's a float
                        # Apply szDecimals truncation (not rounding) to TP size
                        tp1_size = truncate_to_decimals(tp1_size, sz_decimals)
                        
                        # If size becomes 0 after truncation, skip this TP
                        if tp1_size <= 0:
                            await log_message("INFO", f"🎯 Skipping TP1 - size {tp1_perc} truncates to 0 with szDecimals: {sz_decimals}")
                            raise ValueError("TP1 size is 0 after truncation - skipping")
                        
                        await log_message("INFO", f"🎯 Using tp1_perc as size: {tp1_size} (truncated with szDecimals: {sz_decimals})")
                    else:
                        tp1_size = quantity * 0.25  # Default 25% if no size specified
                        tp1_size = truncate_to_decimals(tp1_size, sz_decimals)
                        await log_message("INFO", f"🎯 Using default size (25%): {tp1_size}")
                    
                    # For take profit: if we bought, sell at TP price; if we sold, buy at TP price
                    tp_is_buy = not is_buy  # Opposite of main order
                    
                    # Format TP price using asset-specific formatting (ETH=integer, others=decimal)
                    formatted_tp_price = format_tpsl_price(tp1_target, symbol)
                    
                    # Check if order value meets minimum requirement ($10)
                    order_value = tp1_size * formatted_tp_price
                    if order_value < 10:
                        await log_message("INFO", f"🎯 Skipping TP1 - order value ${order_value:.2f} is below minimum $10 requirement")
                        raise ValueError(f"TP1 order value ${order_value:.2f} is below minimum $10 requirement")
                    
                    await log_message("INFO", f"🎯 Placing TP1: {'BUY' if tp_is_buy else 'SELL'} {tp1_size} {symbol} at ${formatted_tp_price} (original: ${tp1_target}, formatted for {symbol}, value: ${order_value:.2f})")
                    
                    # TRIGGER ORDER: Take Profit as conditional trigger order
                    tp1_order_result = exchange.order(
                        name=symbol,
                        is_buy=tp_is_buy,
                        sz=tp1_size,
                        limit_px=formatted_tp_price,
                        order_type={
                            "trigger": {
                                "triggerPx": formatted_tp_price,
                                "isMarket": True,  # Market execution when triggered
                                "tpsl": "tp"  # Take Profit
                            }
                        }
                        # SEM reduce_only=True - essa foi a chave do sucesso anterior
                        # Removido reduce_only=True para ordens trigger com tpsl
                    )
                    
                    # Check for errors in response (status="ok" doesn't guarantee success)
                    is_success, error_msg = check_order_response_for_errors(tp1_order_result)
                    
                    if is_success:
                        await log_message("INFO", f"✅ TP1 order placed successfully!")
                        await log_message("INFO", f"🎯 TP1 result: {tp1_order_result}")
                        tp_order_results.append({"tp1": tp1_order_result})
                    else:
                        await log_message("ERROR", f"❌ Failed to place TP1 order: {error_msg}")
                        await log_message("ERROR", f"🎯 Full response: {tp1_order_result}")
                        tp_order_results.append({"tp1": {"error": error_msg}})
                    
                except Exception as tp_error:
                    await log_message("ERROR", f"❌ Error placing TP1 order: {str(tp_error)}")
                    tp_order_results.append({"tp1": {"error": str(tp_error)}})
            
            # Handle TP2
            if tp2_price or tp2_perc:
                await log_message("INFO", f"🎯 Setting up take profit 2 order")
                try:
                    # Calculate TP2 price
                    if tp2_price:
                        tp2_target = tp2_price
                    else:
                        # Calculate from percentage
                        entry_price = float(main_order_result.get("response", {}).get("data", {}).get("statuses", [{}])[0].get("filled", {}).get("avgPx", 0))
                        if entry_price > 0:
                            if is_buy:
                                tp2_target = entry_price * (1 + tp2_perc / 100)
                            else:
                                tp2_target = entry_price * (1 - tp2_perc / 100)
                        else:
                            raise ValueError("Could not determine entry price for TP percentage calculation")
                    
                    # Use tp2_perc directly as size (it's not a percentage, but the actual size)
                    if tp2_perc:
                        tp2_size = float(tp2_perc)  # Ensure it's a float
                        # Apply szDecimals truncation (not rounding) to TP size
                        tp2_size = truncate_to_decimals(tp2_size, sz_decimals)
                        
                        # If size becomes 0 after truncation, skip this TP
                        if tp2_size <= 0:
                            await log_message("INFO", f"🎯 Skipping TP2 - size {tp2_perc} truncates to 0 with szDecimals: {sz_decimals}")
                            raise ValueError("TP2 size is 0 after truncation - skipping")
                        
                        await log_message("INFO", f"🎯 Using tp2_perc as size: {tp2_size} (truncated with szDecimals: {sz_decimals})")
                    else:
                        tp2_size = quantity * 0.25  # Default 25% if no size specified
                        tp2_size = truncate_to_decimals(tp2_size, sz_decimals)
                        await log_message("INFO", f"🎯 Using default size (25%): {tp2_size}")
                    
                    # For take profit: if we bought, sell at TP price; if we sold, buy at TP price
                    tp_is_buy = not is_buy  # Opposite of main order
                    
                    # Format TP price using asset-specific formatting (ETH=integer, others=decimal)
                    formatted_tp_price = format_tpsl_price(tp2_target, symbol)
                    
                    # Check if order value meets minimum requirement ($10)
                    order_value = tp2_size * formatted_tp_price
                    if order_value < 10:
                        await log_message("INFO", f"🎯 Skipping TP2 - order value ${order_value:.2f} is below minimum $10 requirement")
                        raise ValueError(f"TP2 order value ${order_value:.2f} is below minimum $10 requirement")
                    
                    await log_message("INFO", f"🎯 Placing TP2: {'BUY' if tp_is_buy else 'SELL'} {tp2_size} {symbol} at ${formatted_tp_price} (original: ${tp2_target}, formatted for {symbol}, value: ${order_value:.2f})")
                    
                    # TRIGGER ORDER: Take Profit as conditional trigger order
                    tp2_order_result = exchange.order(
                        name=symbol,
                        is_buy=tp_is_buy,
                        sz=tp2_size,
                        limit_px=formatted_tp_price,
                        order_type={
                            "trigger": {
                                "triggerPx": formatted_tp_price,
                                "isMarket": False  # False = Limit execution when triggered
                            }
                        },
                        reduce_only=True  # Only reduce existing position
                    )
                    
                    # Check for errors in response (status="ok" doesn't guarantee success)
                    is_success, error_msg = check_order_response_for_errors(tp2_order_result)
                    
                    if is_success:
                        await log_message("INFO", f"✅ TP2 order placed successfully!")
                        await log_message("INFO", f"🎯 TP2 result: {tp2_order_result}")
                        tp_order_results.append({"tp2": tp2_order_result})
                    else:
                        await log_message("ERROR", f"❌ Failed to place TP2 order: {error_msg}")
                        await log_message("ERROR", f"🎯 Full response: {tp2_order_result}")
                        tp_order_results.append({"tp2": {"error": error_msg}})
                    
                except Exception as tp_error:
                    await log_message("ERROR", f"❌ Error placing TP2 order: {str(tp_error)}")
                    tp_order_results.append({"tp2": {"error": str(tp_error)}})
            
            # Handle TP3
            if tp3_price or tp3_perc:
                await log_message("INFO", f"🎯 Setting up take profit 3 order")
                try:
                    # Calculate TP3 price
                    if tp3_price:
                        tp3_target = tp3_price
                    else:
                        # Calculate from percentage
                        entry_price = float(main_order_result.get("response", {}).get("data", {}).get("statuses", [{}])[0].get("filled", {}).get("avgPx", 0))
                        if entry_price > 0:
                            if is_buy:
                                tp3_target = entry_price * (1 + tp3_perc / 100)
                            else:
                                tp3_target = entry_price * (1 - tp3_perc / 100)
                        else:
                            raise ValueError("Could not determine entry price for TP percentage calculation")
                    
                    # Use tp3_perc directly as size (it's not a percentage, but the actual size)
                    if tp3_perc:
                        tp3_size = float(tp3_perc)  # Ensure it's a float
                        # Apply szDecimals truncation (not rounding) to TP size
                        tp3_size = truncate_to_decimals(tp3_size, sz_decimals)
                        
                        # If size becomes 0 after truncation, skip this TP
                        if tp3_size <= 0:
                            await log_message("INFO", f"🎯 Skipping TP3 - size {tp3_perc} truncates to 0 with szDecimals: {sz_decimals}")
                            raise ValueError("TP3 size is 0 after truncation - skipping")
                        
                        await log_message("INFO", f"🎯 Using tp3_perc as size: {tp3_size} (truncated with szDecimals: {sz_decimals})")
                    else:
                        tp3_size = quantity * 0.25  # Default 25% if no size specified
                        tp3_size = truncate_to_decimals(tp3_size, sz_decimals)
                        await log_message("INFO", f"🎯 Using default size (25%): {tp3_size}")
                    
                    # For take profit: if we bought, sell at TP price; if we sold, buy at TP price
                    tp_is_buy = not is_buy  # Opposite of main order
                    
                    # Format TP price using asset-specific formatting (ETH=integer, others=decimal)
                    formatted_tp_price = format_tpsl_price(tp3_target, symbol)
                    
                    # Check if order value meets minimum requirement ($10)
                    order_value = tp3_size * formatted_tp_price
                    if order_value < 10:
                        await log_message("INFO", f"🎯 Skipping TP3 - order value ${order_value:.2f} is below minimum $10 requirement")
                        raise ValueError(f"TP3 order value ${order_value:.2f} is below minimum $10 requirement")
                    
                    await log_message("INFO", f"🎯 Placing TP3: {'BUY' if tp_is_buy else 'SELL'} {tp3_size} {symbol} at ${formatted_tp_price} (original: ${tp3_target}, formatted for {symbol}, value: ${order_value:.2f})")
                    
                    # TRIGGER ORDER: Take Profit as conditional trigger order
                    tp3_order_result = exchange.order(
                        name=symbol,
                        is_buy=tp_is_buy,
                        sz=tp3_size,
                        limit_px=formatted_tp_price,
                        order_type={
                            "trigger": {
                                "triggerPx": formatted_tp_price,
                                "isMarket": False  # False = Limit execution when triggered
                            }
                        },
                        reduce_only=True  # Only reduce existing position
                    )
                    
                    # Check for errors in response (status="ok" doesn't guarantee success)
                    is_success, error_msg = check_order_response_for_errors(tp3_order_result)
                    
                    if is_success:
                        await log_message("INFO", f"✅ TP3 order placed successfully!")
                        await log_message("INFO", f"🎯 TP3 result: {tp3_order_result}")
                        tp_order_results.append({"tp3": tp3_order_result})
                    else:
                        await log_message("ERROR", f"❌ Failed to place TP3 order: {error_msg}")
                        await log_message("ERROR", f"🎯 Full response: {tp3_order_result}")
                        tp_order_results.append({"tp3": {"error": error_msg}})
                    
                except Exception as tp_error:
                    await log_message("ERROR", f"❌ Error placing TP3 order: {str(tp_error)}")
                    tp_order_results.append({"tp3": {"error": str(tp_error)}})
            
            # Handle TP4 - Special handling for complete exit
            if tp4_price or tp4_perc:
                await log_message("INFO", f"🎯 Setting up take profit 4 order (COMPLETE EXIT)")
                try:
                    # Calculate TP4 price
                    if tp4_price:
                        tp4_target = tp4_price
                    else:
                        # Calculate from percentage
                        entry_price = float(main_order_result.get("response", {}).get("data", {}).get("statuses", [{}])[0].get("filled", {}).get("avgPx", 0))
                        if entry_price > 0:
                            if is_buy:
                                tp4_target = entry_price * (1 + tp4_perc / 100)
                            else:
                                tp4_target = entry_price * (1 - tp4_perc / 100)
                        else:
                            raise ValueError("Could not determine entry price for TP percentage calculation")
                    
                    # For TP4, we want to ensure COMPLETE EXIT of the position
                    # Use the provided tp4_perc value and ensure it never exceeds the original strategy value
                    
                    if tp4_perc:
                        # Use the provided tp4_perc value with truncation (not rounding)
                        tp4_size = float(tp4_perc)
                        tp4_size = truncate_to_decimals(tp4_size, sz_decimals)
                        await log_message("INFO", f"🎯 Using provided tp4_perc as size: {tp4_size} (truncated with szDecimals: {sz_decimals})")
                        
                        # If the provided size is too small after truncation, use total quantity
                        if tp4_size <= 0:
                            await log_message("INFO", f"🎯 Provided tp4_perc {tp4_perc} truncates to {tp4_size}, using total quantity for complete exit")
                            tp4_size = quantity  # Use total quantity from webhook to ensure complete exit
                    else:
                        # If no tp4_perc provided, use total quantity for complete exit
                        tp4_size = quantity
                        await log_message("INFO", f"🎯 No tp4_perc provided, using total quantity for complete exit: {tp4_size}")
                    
                    # For take profit: if we bought, sell at TP price; if we sold, buy at TP price
                    tp_is_buy = not is_buy  # Opposite of main order
                    
                    # Format TP price using asset-specific formatting (ETH=integer, others=decimal)
                    formatted_tp_price = format_tpsl_price(tp4_target, symbol)
                    
                    # Check if order value meets minimum requirement ($10)
                    order_value = tp4_size * formatted_tp_price
                    if order_value < 10:
                        await log_message("INFO", f"🎯 Skipping TP4 - order value ${order_value:.2f} is below minimum $10 requirement")
                        raise ValueError(f"TP4 order value ${order_value:.2f} is below minimum $10 requirement")
                    
                    await log_message("INFO", f"🎯 Placing TP4: {'BUY' if tp_is_buy else 'SELL'} {tp4_size} {symbol} at ${formatted_tp_price} (original: ${tp4_target}, formatted for {symbol}, value: ${order_value:.2f}) (COMPLETE EXIT)")
                    
                    # TRIGGER ORDER: Take Profit as conditional trigger order
                    tp4_order_result = exchange.order(
                        name=symbol,
                        is_buy=tp_is_buy,
                        sz=tp4_size,
                        limit_px=formatted_tp_price,
                        order_type={
                            "trigger": {
                                "triggerPx": formatted_tp_price,
                                "isMarket": False  # False = Limit execution when triggered
                            }
                        },
                        reduce_only=True  # Only reduce existing position
                    )
                    
                    # Check for errors in response (status="ok" doesn't guarantee success)
                    is_success, error_msg = check_order_response_for_errors(tp4_order_result)
                    
                    if is_success:
                        await log_message("INFO", f"✅ TP4 order placed successfully!")
                        await log_message("INFO", f"🎯 TP4 result: {tp4_order_result}")
                        tp_order_results.append({"tp4": tp4_order_result})
                    else:
                        await log_message("ERROR", f"❌ Failed to place TP4 order: {error_msg}")
                        await log_message("ERROR", f"🎯 Full response: {tp4_order_result}")
                        tp_order_results.append({"tp4": {"error": error_msg}})
                    
                except Exception as tp_error:
                    await log_message("ERROR", f"❌ Error placing TP4 order: {str(tp_error)}")
                    tp_order_results.append({"tp4": {"error": str(tp_error)}})
            
            # Prepare successful response - ajustado apenas para IMBA_TREND
            order_details_base = {
                "symbol": symbol,
                "side": side,
                "entry_type": entry_type,
                "quantity": quantity,
                "price": price,
                "stop_price": stop_price,
                "tp1_price": tp1_price,
                "tp1_perc": tp1_perc,
            }
            
            # Adicionar TPs adicionais apenas para estratégias que NÃO são IMBA_TREND
            if strategy_id != "IMBA_TREND":
                order_details_base.update({
                    "tp2_price": tp2_price,
                    "tp2_perc": tp2_perc,
                    "tp3_price": tp3_price,
                    "tp3_perc": tp3_perc,
                    "tp4_price": tp4_price,
                    "tp4_perc": tp4_perc,
                })
                
            response_data = {
                "status": "success",
                "message": "Order executed successfully on Hyperliquid",
                "environment": hyperliquid_config.environment,
                "timestamp": get_brazil_time().isoformat(),
                "order_details": order_details_base | {
                    "attempts": attempt,
                    "hyperliquid_response": main_order_result,
                    "stop_loss_response": stop_order_result,
                    "take_profit_responses": tp_order_results
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
            response_data=response_data,
            strategy_id=strategy_id
        )
        await db.hyperliquid_responses.insert_one(hl_response.dict())
        
        await log_message("INFO", f"💾 Response stored with webhook_id: {webhook_id} [Strategy: {strategy_id}]")
        
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
            response_data=error_response,
            strategy_id=strategy_id
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

@api_router.get("/status")
async def get_status():
    """Get server status and statistics"""
    try:
        # Get balance and wallet address
        balance_result = await get_cached_balance()
        if isinstance(balance_result, tuple) and len(balance_result) == 2:
            wallet_address, balance = balance_result
        else:
            wallet_address = "Error"
            balance = 0.0
        
        # Calculate uptime percentage
        uptime_percentage = get_uptime_percentage()
        
        # Calculate server runtime
        current_time = get_brazil_time()
        uptime_duration = current_time - server_start_time
        uptime_seconds = int(uptime_duration.total_seconds())
        
        # Format uptime
        hours = uptime_seconds // 3600
        minutes = (uptime_seconds % 3600) // 60
        seconds = uptime_seconds % 60
        uptime_formatted = f"{hours:02d}h {minutes:02d}m {seconds:02d}s"
        
        # Calculate uptime percentage
        uptime_percentage = get_uptime_percentage()
        
        # Format monitoring since timestamp
        if uptime_stats['monitoring_start_time']:
            monitoring_since_formatted = uptime_stats['monitoring_start_time']
        else:
            monitoring_since_formatted = "Starting..."
        
        return {
            "status": "running",
            "environment": hyperliquid_config.environment,
            "uptime": uptime_formatted,
            "balance": balance,
            "wallet_address": wallet_address,
            "hyperliquid_connected": True,
            "statistics": {
                "total_webhooks": stats['total_webhooks'],
                "successful_forwards": stats['successful_forwards'],
                "failed_forwards": stats['failed_forwards'],
                "success_rate": f"{(stats['successful_forwards'] / max(stats['total_webhooks'], 1)) * 100:.1f}%"
            },
            "uptime_monitoring": {
                "percentage": f"{uptime_percentage:.1f}%",
                "total_pings": uptime_stats['total_pings'],
                "successful_pings": uptime_stats['successful_pings'],
                "failed_pings": uptime_stats['total_pings'] - uptime_stats['successful_pings'],
                "monitoring_since": monitoring_since_formatted
            }
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "environment": hyperliquid_config.environment,
            "uptime": "unknown",
            "balance": "error",
            "wallet_address": "error",
            "hyperliquid_connected": False,
            "statistics": {
                "total_webhooks": stats['total_webhooks'],
                "successful_forwards": stats['successful_forwards'],
                "failed_forwards": stats['failed_forwards'],
                "success_rate": f"{(stats['successful_forwards'] / max(stats['total_webhooks'], 1)) * 100:.1f}%"
            },
            "uptime_monitoring": {
                "percentage": f"{get_uptime_percentage():.1f}%",
                "total_pings": uptime_stats['total_pings'],
                "successful_pings": uptime_stats['successful_pings'],
                "failed_pings": uptime_stats['total_pings'] - uptime_stats['successful_pings'],
                "monitoring_since": uptime_stats.get('monitoring_start_time', get_brazil_time()).strftime('%Y-%m-%d %H:%M:%S')
            }
        }

@api_router.get("/logs")
async def get_logs(limit: int = 100, level: Optional[str] = None):
    """Get recent logs (max 1000)"""
    try:
        # Limit maximum to 1000 to prevent performance issues
        if limit > 1000:
            limit = 1000
            
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
async def get_webhooks(limit: int = 50, strategy_ids: Optional[str] = None):
    """Get recent webhooks with optional strategy filtering"""
    try:
        # Build filter query based on strategy_ids
        filter_query = {}
        
        if strategy_ids:
            # Parse comma-separated strategy_ids
            strategy_list = [s.strip() for s in strategy_ids.split(',') if s.strip()]
            if strategy_list:
                filter_query["strategy_id"] = {"$in": strategy_list}
        
        # Use _id for sorting to ensure proper chronological order
        # _id contains timestamp information and is always in chronological order
        webhooks = await db.webhooks.find(filter_query).sort("_id", -1).limit(limit).to_list(limit)
        
        # Convert to JSON-serializable format
        webhooks_data = []
        for webhook in webhooks:
            webhook_data = {
                "id": webhook.get("id"),
                "timestamp": webhook.get("timestamp"),
                "source": webhook.get("source"),
                "payload": webhook.get("payload"),
                "status": webhook.get("status"),
                "error": webhook.get("error"),
                "strategy_id": webhook.get("strategy_id", "OTHERS")
            }
            webhooks_data.append(webhook_data)
            
        return {"webhooks": webhooks_data}
        
    except Exception as e:
        await log_message("ERROR", f"Failed to get webhooks: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/reset-uptime-stats")
async def reset_uptime_statistics():
    """Reset uptime monitoring statistics"""
    try:
        reset_uptime_stats()
        await log_message("INFO", "🔄 Uptime statistics reset")
        
        return {
            "status": "success", 
            "message": "Uptime statistics reset successfully",
            "timestamp": get_brazil_time().isoformat()
        }
        
    except Exception as e:
        await log_message("ERROR", f"Failed to reset uptime stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/reset-uptime-stats")
async def reset_uptime_statistics():
    """Reset uptime monitoring statistics"""
    try:
        reset_uptime_stats()
        await log_message("INFO", "🔄 Uptime statistics reset")
        
        return {
            "status": "success", 
            "message": "Uptime statistics reset successfully",
            "timestamp": get_brazil_time().isoformat()
        }
        
    except Exception as e:
        await log_message("ERROR", f"Failed to reset uptime stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
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
async def get_hyperliquid_responses(limit: int = 50, strategy_ids: Optional[str] = None):
    """Get recent Hyperliquid responses with optional strategy filtering"""
    try:
        # Build filter query based on strategy_ids
        filter_query = {}
        
        if strategy_ids:
            # Parse comma-separated strategy_ids
            strategy_list = [s.strip() for s in strategy_ids.split(',') if s.strip()]
            if strategy_list:
                filter_query["strategy_id"] = {"$in": strategy_list}
        
        # Use _id for sorting to ensure proper chronological order
        responses = await db.hyperliquid_responses.find(filter_query).sort("_id", -1).limit(limit).to_list(limit)
        
        # Convert to JSON-serializable format
        responses_data = []
        for response in responses:
            response_data = {
                "id": response.get("id"),
                "timestamp": response.get("timestamp"),
                "webhook_id": response.get("webhook_id"),
                "response_data": response.get("response_data"),
                "status": response.get("status"),
                "error": response.get("error"),
                "strategy_id": response.get("strategy_id", "OTHERS")
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

# Strategy Management Endpoints
@api_router.get("/strategies")
async def get_strategies():
    """Get all strategies with their configurations"""
    try:
        strategies = strategy_manager.strategies
        
        # Get statistics for each strategy
        strategy_data = {}
        for strategy_id, config in strategies.items():
            # Get webhook count for this strategy
            webhook_count = await db.webhooks.count_documents({"strategy_id": strategy_id})
            
            # Get response count for this strategy
            response_count = await db.hyperliquid_responses.count_documents({"strategy_id": strategy_id})
            
            strategy_data[strategy_id] = {
                "id": strategy_id,
                "name": config.get("name", strategy_id),
                "enabled": config.get("enabled", True),
                "rules": config.get("rules", {}),
                "stats": {
                    "total_webhooks": webhook_count,
                    "total_responses": response_count
                }
            }
        
        return {"strategies": strategy_data}
        
    except Exception as e:
        await log_message("ERROR", f"Failed to get strategies: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/strategies/ids")
async def get_strategy_ids():
    """Get all known strategy IDs for filtering"""
    try:
        # Get strategy IDs from strategy manager
        manager_ids = strategy_manager.get_all_strategy_ids()
        
        # Also get any strategy IDs from the database that might not be in manager
        webhook_ids = await db.webhooks.distinct("strategy_id")
        response_ids = await db.hyperliquid_responses.distinct("strategy_id")
        
        # Combine all IDs and remove duplicates
        all_ids = set(manager_ids + webhook_ids + response_ids)
        
        # Remove None values and ensure OTHERS is included
        strategy_ids = [sid for sid in all_ids if sid is not None]
        if "OTHERS" not in strategy_ids:
            strategy_ids.append("OTHERS")
        
        # Sort for consistent ordering
        strategy_ids.sort()
        
        return {"strategy_ids": strategy_ids}
        
    except Exception as e:
        await log_message("ERROR", f"Failed to get strategy IDs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/strategies/{strategy_id}/toggle")
async def toggle_strategy(strategy_id: str):
    """Toggle strategy enabled/disabled status"""
    try:
        if strategy_id not in strategy_manager.strategies:
            raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
        
        current_status = strategy_manager.strategies[strategy_id].get("enabled", True)
        new_status = not current_status
        
        strategy_manager.strategies[strategy_id]["enabled"] = new_status
        
        await log_message("INFO", f"⚙️ Strategy {strategy_id} {'enabled' if new_status else 'disabled'}")
        
        return {
            "strategy_id": strategy_id,
            "enabled": new_status,
            "message": f"Strategy {strategy_id} {'enabled' if new_status else 'disabled'}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await log_message("ERROR", f"Failed to toggle strategy {strategy_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/strategies/{strategy_id}")
async def get_strategy(strategy_id: str):
    """Get specific strategy configuration"""
    try:
        if strategy_id not in strategy_manager.strategies:
            # Auto-create if not exists
            strategy_manager.add_strategy(strategy_id)
        
        config = strategy_manager.get_strategy(strategy_id)
        
        # Get statistics for this strategy
        webhook_count = await db.webhooks.count_documents({"strategy_id": strategy_id})
        response_count = await db.hyperliquid_responses.count_documents({"strategy_id": strategy_id})
        
        return {
            "id": strategy_id,
            "name": config.get("name", strategy_id),
            "enabled": config.get("enabled", True),
            "rules": config.get("rules", {}),
            "stats": {
                "total_webhooks": webhook_count,
                "total_responses": response_count
            }
        }
        
    except Exception as e:
        await log_message("ERROR", f"Failed to get strategy {strategy_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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
    global uptime_task
    await log_message("INFO", "TradingView to Hyperliquid Middleware Server Starting")
    await test_hyperliquid_connection()
    
    # Load existing uptime data from database (survives container restarts)
    await load_persistent_uptime_stats()
    
    # Start uptime monitoring task
    uptime_task = asyncio.create_task(ping_uptime_monitor())
    await log_message("INFO", "🔄 Uptime monitoring started")

@app.on_event("shutdown")
async def shutdown_db_client():
    global uptime_task
    await log_message("INFO", "Server shutting down")
    
    # Cancel uptime monitoring task
    if uptime_task:
        uptime_task.cancel()
        await log_message("INFO", "🔄 Uptime monitoring stopped")
    
    client.close()