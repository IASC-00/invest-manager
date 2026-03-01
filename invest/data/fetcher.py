"""Async orchestrator that fetches prices from appropriate sources."""
import asyncio
import logging
from typing import Optional

from invest.db.models import AssetType, Position
from invest.data.sources.coingecko_source import fetch_crypto_price, fetch_crypto_ohlcv
from invest.data.sources.yfinance_source import fetch_current_price, fetch_ohlcv

import pandas as pd

logger = logging.getLogger(__name__)


async def fetch_price_for_position(pos: Position) -> tuple[str, dict]:
    """Fetch current price for a single position, routing by asset_type."""
    symbol = pos.symbol
    try:
        if pos.asset_type == AssetType.CRYPTO:
            price_info = await fetch_crypto_price(symbol)
        else:
            # STOCK, ETF, OPTION, BOND
            price_info = await fetch_current_price(symbol)
    except Exception as e:
        logger.error("Price fetch error for %s: %s", symbol, e)
        price_info = {"price": None, "prev_close": None, "day_change": None, "day_change_pct": None}

    return symbol, price_info


async def fetch_all_prices(positions: list[Position]) -> dict[str, dict]:
    """Fetch prices for all positions concurrently."""
    tasks = [fetch_price_for_position(p) for p in positions]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    price_map: dict[str, dict] = {}
    for r in results:
        if isinstance(r, Exception):
            logger.error("Price fetch task failed: %s", r)
            continue
        symbol, info = r
        price_map[symbol] = info

    return price_map


async def fetch_ohlcv_for_symbol(symbol: str, asset_type: AssetType, period: str = "3mo") -> pd.DataFrame:
    """Fetch historical OHLCV for anomaly detection."""
    if asset_type == AssetType.CRYPTO:
        records = await fetch_crypto_ohlcv(symbol, days=90)
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        return df
    else:
        return await fetch_ohlcv(symbol, period=period)


async def fetch_market_pulse() -> dict[str, dict]:
    """Fetch key market benchmark prices: SPY, QQQ, BTC, VIX proxy."""
    benchmarks = ["SPY", "QQQ", "^VIX", "GLD"]
    tasks = [fetch_current_price(s) for s in benchmarks]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    pulse = {}
    for sym, r in zip(benchmarks, results):
        if isinstance(r, Exception):
            pulse[sym] = {"price": None}
        else:
            pulse[sym] = r

    btc_price = await fetch_crypto_price("BTC")
    pulse["BTC"] = btc_price
    return pulse
