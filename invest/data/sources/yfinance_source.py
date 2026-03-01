"""yfinance data source — stocks, ETFs, options chains."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential

from invest.config import settings
from invest.data.cache import price_cache

logger = logging.getLogger(__name__)


def _utc_now_naive() -> datetime:
    return datetime.utcnow()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def _fetch_ticker_sync(symbol: str, period: str = "3mo") -> pd.DataFrame:
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, auto_adjust=True)
    return df


async def fetch_ohlcv(symbol: str, period: str = "3mo") -> pd.DataFrame:
    """Fetch OHLCV for a stock/ETF symbol, using cache when fresh."""
    cached = await price_cache.get(symbol, "yfinance", settings.cache_ttl_ohlcv)
    if cached:
        df = pd.DataFrame(cached)
        df = df.set_index("timestamp").sort_index()
        return df

    try:
        df = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _fetch_ticker_sync(symbol, period)
        )
    except Exception as e:
        logger.error("yfinance fetch failed for %s: %s", symbol, e)
        return pd.DataFrame()

    if df.empty:
        return df

    # Normalise column names
    df.index = df.index.tz_localize(None) if df.index.tz is not None else df.index
    records = []
    for ts, row in df.iterrows():
        records.append(
            {
                "timestamp": ts.to_pydatetime(),
                "open": float(row.get("Open", 0) or 0),
                "high": float(row.get("High", 0) or 0),
                "low": float(row.get("Low", 0) or 0),
                "close": float(row.get("Close", 0) or 0),
                "volume": float(row.get("Volume", 0) or 0),
            }
        )

    await price_cache.store(symbol, "yfinance", records)
    return df


async def fetch_current_price(symbol: str) -> dict:
    """
    Return {price, prev_close, day_change, day_change_pct, volume}.
    Uses fast_info for speed; falls back to history.
    """
    try:
        ticker = await asyncio.get_event_loop().run_in_executor(
            None, lambda: yf.Ticker(symbol)
        )
        info = await asyncio.get_event_loop().run_in_executor(
            None, lambda: ticker.fast_info
        )
        price = getattr(info, "last_price", None) or getattr(info, "regularMarketPrice", None)
        prev_close = getattr(info, "previous_close", None) or getattr(info, "regularMarketPreviousClose", None)

        if price is None:
            # Fallback to history
            df = await asyncio.get_event_loop().run_in_executor(
                None, lambda: ticker.history(period="2d")
            )
            if not df.empty:
                price = float(df["Close"].iloc[-1])
                prev_close = float(df["Close"].iloc[-2]) if len(df) > 1 else price

        result = {"price": float(price) if price else None, "prev_close": float(prev_close) if prev_close else None}
        if result["price"] and result["prev_close"] and result["prev_close"] != 0:
            result["day_change"] = result["price"] - result["prev_close"]
            result["day_change_pct"] = result["day_change"] / result["prev_close"] * 100
        else:
            result["day_change"] = None
            result["day_change_pct"] = None
        return result

    except Exception as e:
        logger.error("fetch_current_price failed for %s: %s", symbol, e)
        return {"price": None, "prev_close": None, "day_change": None, "day_change_pct": None}


async def fetch_options_activity(symbol: str) -> dict:
    """
    Fetch put/call ratio and detect sweeps.
    Returns {"put_call_ratio": float, "sweep": bool, "detail": dict}
    """
    try:
        ticker = await asyncio.get_event_loop().run_in_executor(
            None, lambda: yf.Ticker(symbol)
        )
        expiries = await asyncio.get_event_loop().run_in_executor(
            None, lambda: ticker.options
        )
        if not expiries:
            return {"put_call_ratio": None, "sweep": False, "detail": {}}

        # Use nearest expiry
        chain = await asyncio.get_event_loop().run_in_executor(
            None, lambda: ticker.option_chain(expiries[0])
        )
        calls = chain.calls
        puts = chain.puts

        call_vol = float(calls["volume"].sum()) if not calls.empty else 0
        put_vol = float(puts["volume"].sum()) if not puts.empty else 0
        put_call_ratio = (put_vol / call_vol) if call_vol > 0 else None

        # Sweep detection: vol > 50% of open interest
        sweep = False
        detail: dict = {"call_volume": call_vol, "put_volume": put_vol}

        for df, side in [(calls, "call"), (puts, "put")]:
            if df.empty:
                continue
            df = df.copy()
            df["oi"] = df["openInterest"].fillna(0)
            df["vol"] = df["volume"].fillna(0)
            sweeps = df[df["oi"] > 0][lambda x: x["vol"] > 0.5 * x["oi"]]
            if not sweeps.empty:
                sweep = True
                detail[f"{side}_sweeps"] = len(sweeps)

        return {"put_call_ratio": put_call_ratio, "sweep": sweep, "detail": detail}

    except Exception as e:
        logger.warning("Options fetch failed for %s: %s", symbol, e)
        return {"put_call_ratio": None, "sweep": False, "detail": {"error": str(e)}}
