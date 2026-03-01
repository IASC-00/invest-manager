"""CoinGecko data source for crypto assets."""
import asyncio
import logging
from datetime import datetime

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from invest.config import settings
from invest.data.cache import price_cache

logger = logging.getLogger(__name__)

# Map common ticker symbols to CoinGecko IDs
SYMBOL_TO_ID: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "XRP": "ripple",
    "DOT": "polkadot",
    "AVAX": "avalanche-2",
    "MATIC": "matic-network",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
    "ATOM": "cosmos",
    "FTM": "fantom",
}

BASE_URL = "https://api.coingecko.com/api/v3"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
async def _get(path: str, params: dict | None = None) -> dict | list:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{BASE_URL}{path}", params=params or {})
        r.raise_for_status()
        return r.json()


def _symbol_to_id(symbol: str) -> str:
    return SYMBOL_TO_ID.get(symbol.upper(), symbol.lower())


async def fetch_crypto_price(symbol: str) -> dict:
    """Return {price, prev_close, day_change_pct} for a crypto symbol."""
    cached = await price_cache.get(symbol, "coingecko", settings.cache_ttl_crypto)
    if cached:
        latest = cached[0]
        return {
            "price": latest["close"],
            "prev_close": None,
            "day_change": None,
            "day_change_pct": None,
        }

    coin_id = _symbol_to_id(symbol)
    try:
        data = await _get(
            "/simple/price",
            {
                "ids": coin_id,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_24hr_vol": "true",
            },
        )
        info = data.get(coin_id, {})
        price = info.get("usd")
        day_change_pct = info.get("usd_24h_change")

        if price is not None:
            record = {
                "timestamp": datetime.utcnow(),
                "close": float(price),
                "open": None,
                "high": None,
                "low": None,
                "volume": info.get("usd_24h_vol"),
            }
            await price_cache.store(symbol, "coingecko", [record])

        prev_close = None
        if price and day_change_pct is not None:
            prev_close = price / (1 + day_change_pct / 100)

        return {
            "price": float(price) if price else None,
            "prev_close": float(prev_close) if prev_close else None,
            "day_change": float(price - prev_close) if (price and prev_close) else None,
            "day_change_pct": float(day_change_pct) if day_change_pct else None,
        }

    except Exception as e:
        logger.error("CoinGecko fetch failed for %s: %s", symbol, e)
        return {"price": None, "prev_close": None, "day_change": None, "day_change_pct": None}


async def fetch_crypto_ohlcv(symbol: str, days: int = 90) -> list[dict]:
    """Fetch historical OHLCV for anomaly detection."""
    cached = await price_cache.get(symbol, "coingecko", settings.cache_ttl_crypto)
    if cached and len(cached) >= 30:
        return cached

    coin_id = _symbol_to_id(symbol)
    try:
        data = await _get(f"/coins/{coin_id}/ohlc", {"vs_currency": "usd", "days": str(days)})
        # Each entry: [timestamp_ms, open, high, low, close]
        records = []
        for entry in data:
            ts = datetime.utcfromtimestamp(entry[0] / 1000)
            records.append(
                {
                    "timestamp": ts,
                    "open": float(entry[1]),
                    "high": float(entry[2]),
                    "low": float(entry[3]),
                    "close": float(entry[4]),
                    "volume": None,
                }
            )
        await price_cache.store(symbol, "coingecko", records)
        return records

    except Exception as e:
        logger.error("CoinGecko OHLCV failed for %s: %s", symbol, e)
        return []


async def fetch_cross_exchange_spread(symbol: str) -> dict:
    """
    Approximate cross-exchange divergence using CoinGecko exchange tickers.
    Returns {spread_pct, high_price, low_price, exchanges}.
    """
    coin_id = _symbol_to_id(symbol)
    try:
        data = await _get(f"/coins/{coin_id}/tickers", {"include_exchange_logo": "false"})
        tickers = data.get("tickers", [])
        usd_tickers = [
            t for t in tickers
            if t.get("target", "").upper() in ("USD", "USDT", "USDC", "BUSD")
            and t.get("last") and float(t["last"]) > 0
        ]
        if len(usd_tickers) < 2:
            return {"spread_pct": 0.0, "high_price": None, "low_price": None, "exchanges": []}

        prices = [(t["market"]["name"], float(t["last"])) for t in usd_tickers[:10]]
        price_vals = [p for _, p in prices]
        high = max(price_vals)
        low = min(price_vals)
        spread_pct = (high - low) / low * 100 if low > 0 else 0.0

        return {
            "spread_pct": spread_pct,
            "high_price": high,
            "low_price": low,
            "exchanges": [name for name, _ in prices],
        }

    except Exception as e:
        logger.warning("Cross-exchange spread failed for %s: %s", symbol, e)
        return {"spread_pct": 0.0, "high_price": None, "low_price": None, "exchanges": []}
