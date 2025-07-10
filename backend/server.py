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
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants
import json
import asyncio
from collections import defaultdict

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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source: str = "tradingview"
    payload: Dict[str, Any]
    status: str = "received"
    error: Optional[str] = None

class HyperliquidResponse(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    webhook_id: str
    response_data: Dict[str, Any]
    status: str = "sent"
    error: Optional[str] = None

class ServerStatus(BaseModel):
    status: str
    environment: str
    timestamp: datetime
    uptime: str
    total_webhooks: int
    successful_forwards: int
    failed_forwards: int
    hyperliquid_connected: bool
    balance: Optional[float] = None
    wallet_address: Optional[str] = None
    
class LogEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    level: str
    message: str
    details: Optional[Dict[str, Any]] = None

# Global stats
stats = defaultdict(int)
server_start_time = datetime.utcnow()

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

async def get_wallet_address():
    """Get wallet address from private key"""
    try:
        if not hyperliquid_config.private_key:
            return None
            
        from eth_account import Account
        account = Account.from_key(hyperliquid_config.private_key)
        return account.address
        
    except Exception as e:
        await log_message("ERROR", f"Failed to get wallet address: {str(e)}")
        return None

async def get_account_balance():
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
        # Get the payload
        payload = await request.json()
        
        # Log the incoming webhook
        webhook_msg = WebhookMessage(payload=payload)
        await db.webhooks.insert_one(webhook_msg.dict())
        stats['total_webhooks'] += 1
        
        await log_message("INFO", "TradingView webhook received", {"payload": payload})
        
        # Forward to Hyperliquid
        try:
            hyperliquid_response = await forward_to_hyperliquid(webhook_msg.id, payload)
            stats['successful_forwards'] += 1
            
            return {
                "status": "success",
                "webhook_id": webhook_msg.id,
                "message": "Webhook processed and forwarded to Hyperliquid",
                "hyperliquid_response": hyperliquid_response
            }
            
        except Exception as e:
            stats['failed_forwards'] += 1
            await log_message("ERROR", f"Failed to forward to Hyperliquid: {str(e)}")
            
            # Update webhook status
            await db.webhooks.update_one(
                {"id": webhook_msg.id},
                {"$set": {"status": "failed", "error": str(e)}}
            )
            
            raise HTTPException(status_code=500, detail=f"Failed to forward to Hyperliquid: {str(e)}")
            
    except Exception as e:
        await log_message("ERROR", f"Webhook processing failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def forward_to_hyperliquid(webhook_id: str, payload: Dict[str, Any]):
    """Forward the webhook payload to Hyperliquid"""
    try:
        # For now, we'll just log the payload and simulate forwarding
        # In a real implementation, you would parse the payload and execute trades
        
        await log_message("INFO", f"Forwarding webhook {webhook_id} to Hyperliquid", {"payload": payload})
        
        # Simulate response (in real implementation, this would be actual trading response)
        response_data = {
            "status": "simulated",
            "message": "Webhook forwarded to Hyperliquid (simulated)",
            "environment": hyperliquid_config.environment,
            "timestamp": datetime.utcnow().isoformat(),
            "original_payload": payload
        }
        
        # Store the response
        hl_response = HyperliquidResponse(
            webhook_id=webhook_id,
            response_data=response_data
        )
        await db.hyperliquid_responses.insert_one(hl_response.dict())
        
        return response_data
        
    except Exception as e:
        await log_message("ERROR", f"Failed to forward to Hyperliquid: {str(e)}")
        raise

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
        uptime = datetime.utcnow() - server_start_time
        uptime_str = f"{uptime.days}d {uptime.seconds//3600}h {(uptime.seconds//60)%60}m"
        
        status = ServerStatus(
            status="running",
            environment=hyperliquid_config.environment,
            timestamp=datetime.utcnow(),
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
    client.close()
    await log_message("INFO", "Server shutting down")