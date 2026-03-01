"""Pydantic v2 schemas for portfolio operations."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from invest.db.models import AlertLevel, AssetType, OptionType, TransactionType


class PositionCreate(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    asset_type: AssetType = AssetType.STOCK
    quantity: float = Field(..., gt=0)
    avg_cost: float = Field(..., gt=0)
    currency: str = Field(default="USD", max_length=10)
    notes: Optional[str] = None
    # Options
    option_type: Optional[OptionType] = None
    strike: Optional[float] = None
    expiry: Optional[datetime] = None
    underlying: Optional[str] = None

    @model_validator(mode="after")
    def validate_options(self):
        if self.asset_type == AssetType.OPTION:
            if not all([self.option_type, self.strike, self.expiry, self.underlying]):
                raise ValueError(
                    "Options require option_type, strike, expiry, and underlying"
                )
        return self


class PositionOut(BaseModel):
    id: int
    symbol: str
    asset_type: AssetType
    quantity: float
    avg_cost: float
    currency: str
    opened_at: datetime
    is_active: bool
    notes: Optional[str] = None
    option_type: Optional[OptionType] = None
    strike: Optional[float] = None
    expiry: Optional[datetime] = None
    underlying: Optional[str] = None

    model_config = {"from_attributes": True}


class TransactionCreate(BaseModel):
    position_id: int
    tx_type: TransactionType
    quantity: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    fees: float = Field(default=0.0, ge=0)
    notes: Optional[str] = None


class PositionWithPnL(BaseModel):
    position: PositionOut
    current_price: Optional[float] = None
    market_value: Optional[float] = None
    cost_basis: float
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    day_change: Optional[float] = None
    day_change_pct: Optional[float] = None

    model_config = {"from_attributes": True}


class AlertOut(BaseModel):
    id: int
    symbol: str
    detector: str
    level: AlertLevel
    title: str
    detail_json: str
    ai_analysis: Optional[str] = None
    ai_score: Optional[float] = None
    fired_at: datetime
    acknowledged: bool

    model_config = {"from_attributes": True}
