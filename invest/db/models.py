"""SQLAlchemy ORM models."""
import enum
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey, Integer,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AssetType(str, enum.Enum):
    STOCK = "stock"
    ETF = "etf"
    CRYPTO = "crypto"
    OPTION = "option"
    BOND = "bond"
    CASH = "cash"


class OptionType(str, enum.Enum):
    CALL = "call"
    PUT = "put"


class AlertLevel(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class TransactionType(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    asset_type: Mapped[AssetType] = mapped_column(Enum(AssetType), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    avg_cost: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Options-specific fields
    option_type: Mapped[OptionType | None] = mapped_column(Enum(OptionType), nullable=True)
    strike: Mapped[float | None] = mapped_column(Float, nullable=True)
    expiry: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    underlying: Mapped[str | None] = mapped_column(String(20), nullable=True)

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="position", cascade="all, delete-orphan"
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"), nullable=False)
    tx_type: Mapped[TransactionType] = mapped_column(Enum(TransactionType), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    position: Mapped["Position"] = relationship(back_populates="transactions")


class PriceRecord(Base):
    __tablename__ = "price_records"
    __table_args__ = (
        UniqueConstraint("symbol", "timestamp", "source", name="uq_price_record"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False)  # yfinance/coingecko/fred
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    detector: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[AlertLevel] = mapped_column(Enum(AlertLevel), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    detail_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    ai_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fired_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)


class AIInsight(Base):
    __tablename__ = "ai_insights"
    __table_args__ = (
        UniqueConstraint("prompt_hash", name="uq_prompt_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256
    model: Mapped[str] = mapped_column(String(60), nullable=False)
    prompt_summary: Mapped[str] = mapped_column(String(200), nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
