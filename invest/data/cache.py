"""SQLite TTL cache for API responses."""
import asyncio
import json
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Optional

from sqlalchemy import delete, select, text

from invest.db.engine import get_session
from invest.db.models import PriceRecord


class PriceCache:
    """Cache OHLCV data in PriceRecord table, checking freshness by TTL."""

    async def get(
        self,
        symbol: str,
        source: str,
        ttl_seconds: int,
    ) -> Optional[list[dict]]:
        """Return cached records if fresh, else None."""
        cutoff = datetime.fromtimestamp(time.time() - ttl_seconds, tz=timezone.utc).replace(tzinfo=None)
        async with get_session() as session:
            result = await session.execute(
                select(PriceRecord)
                .where(
                    PriceRecord.symbol == symbol,
                    PriceRecord.source == source,
                    PriceRecord.fetched_at >= cutoff,
                )
                .order_by(PriceRecord.timestamp.desc())
                .limit(100)
            )
            rows = result.scalars().all()
        if not rows:
            return None
        return [
            {
                "timestamp": r.timestamp,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in rows
        ]

    async def store(
        self,
        symbol: str,
        source: str,
        records: list[dict],
    ) -> None:
        """Upsert price records into the cache table."""
        if not records:
            return
        async with get_session() as session:
            for rec in records:
                # Check for existing record
                existing = await session.execute(
                    select(PriceRecord).where(
                        PriceRecord.symbol == symbol,
                        PriceRecord.timestamp == rec["timestamp"],
                        PriceRecord.source == source,
                    )
                )
                row = existing.scalar_one_or_none()
                if row is None:
                    session.add(
                        PriceRecord(
                            symbol=symbol,
                            timestamp=rec["timestamp"],
                            open=rec.get("open"),
                            high=rec.get("high"),
                            low=rec.get("low"),
                            close=rec["close"],
                            volume=rec.get("volume"),
                            source=source,
                        )
                    )
                else:
                    row.close = rec["close"]
                    row.fetched_at = datetime.utcnow()


price_cache = PriceCache()
