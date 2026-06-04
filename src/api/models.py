"""Pydantic request/response models for the API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# === Wallet ===

class CreateWalletRequest(BaseModel):
    chain: str = Field("ethereum", description="Chain name")


class ImportWalletRequest(BaseModel):
    private_key: str = Field(..., description="Private key (hex)")
    chain: str = Field("ethereum", description="Chain name")


class WalletResponse(BaseModel):
    address: str
    chain: str
    balance: Optional[str] = None


# === Swap ===

class SwapRequest(BaseModel):
    chain: str = Field("ethereum", description="Chain name")
    token_in: str = Field(..., description="Input token address or symbol")
    token_out: str = Field(..., description="Output token address or symbol")
    amount_in: str = Field(..., description="Amount to swap (human-readable)")
    slippage: float = Field(0.5, description="Slippage tolerance (%)")
    private_key: Optional[str] = Field(None, description="Private key for signing")


class SwapQuoteResponse(BaseModel):
    token_in: str
    token_out: str
    amount_in: str
    estimated_out: str
    price_impact: float
    route: List[str]


# === Portfolio ===

class PortfolioRequest(BaseModel):
    chain: str = Field("ethereum", description="Chain name")
    address: Optional[str] = Field(None, description="Wallet address (uses configured if None)")


class PortfolioResponse(BaseModel):
    address: str
    chain: str
    native_balance: str
    native_symbol: str
    tokens: List[Dict[str, Any]]
    total_value_usd: float


# === Gas ===

class GasRequest(BaseModel):
    chain: str = Field("ethereum", description="Chain name")


class GasResponse(BaseModel):
    chain: str
    base_fee: int
    low: Dict[str, Any]
    medium: Dict[str, Any]
    high: Dict[str, Any]
    recommendation: str


# === Watcher ===

class WatchRequest(BaseModel):
    address: str = Field(..., description="Wallet address to watch")
    chain: str = Field("ethereum", description="Chain name")
    label: str = Field("", description="Label for the watched address")
    tags: List[str] = Field(default_factory=list, description="Tags (whale, protocol, etc)")


class AlertRequest(BaseModel):
    severity: str = Field("medium", description="Alert severity level")
    message: str = Field(..., description="Alert message")


# === Approval ===

class ApprovalScanRequest(BaseModel):
    chain: str = Field("ethereum", description="Chain name")
    address: Optional[str] = Field(None, description="Wallet address")


class RevokeRequest(BaseModel):
    chain: str = Field("ethereum", description="Chain name")
    token: str = Field(..., description="Token address")
    spender: str = Field(..., description="Spender address")
    private_key: Optional[str] = Field(None, description="Private key for signing")


# === DCA ===

class DCAOrderRequest(BaseModel):
    chain: str = Field("ethereum", description="Chain name")
    token_in: str = Field(..., description="Input token (e.g. USDC)")
    token_out: str = Field(..., description="Output token (e.g. ETH)")
    amount_per_buy: str = Field(..., description="Amount per buy")
    frequency: str = Field("daily", description="Frequency: hourly/daily/weekly/monthly")
    total_buys: Optional[int] = Field(None, description="Total number of buys (None = unlimited)")


class DCAStatusResponse(BaseModel):
    order_id: str
    status: str
    buys_executed: int
    total_buys: Optional[int]
    avg_price: Optional[float]
    total_spent: str


# === Yield ===

class YieldScanRequest(BaseModel):
    chain: str = Field("ethereum", description="Chain name")
    category: Optional[str] = Field(None, description="Protocol category (lending, dex, etc)")
    min_apy: float = Field(0.0, description="Minimum APY (%)")
    min_tvl: float = Field(0.0, description="Minimum TVL (USD)")


class YieldResponse(BaseModel):
    protocol: str
    chain: str
    apy: float
    tvl: float
    category: str
    token: str


# === Bridge ===

class BridgeRequest(BaseModel):
    from_chain: str = Field(..., description="Source chain")
    to_chain: str = Field(..., description="Destination chain")
    token: str = Field(..., description="Token to bridge")
    amount: str = Field(..., description="Amount to bridge")
    from_address: Optional[str] = Field(None, description="Sender address")


class BridgeQuoteResponse(BaseModel):
    from_chain: str
    to_chain: str
    token: str
    amount: str
    estimated_receive: str
    bridge_fee: str
    estimated_time: str
    route: str
