"""FRED (Federal Reserve Economic Data) source for macro/bonds."""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from invest.config import settings

logger = logging.getLogger(__name__)

# Key FRED series
SERIES = {
    "DGS10": "10Y Treasury Yield",
    "DGS2": "2Y Treasury Yield",
    "DGS1MO": "1M Treasury Yield",
    "VIXCLS": "VIX Volatility Index",
    "FEDFUNDS": "Fed Funds Rate",
    "DCOILWTICO": "WTI Crude Oil",
    "BAMLH0A0HYM2": "HY Spread (ICE BofA)",
}


async def fetch_macro_data(series_ids: list[str] | None = None) -> dict[str, dict]:
    """
    Fetch latest values for FRED series.
    Returns {series_id: {value, date, description}}.
    Requires FRED_API_KEY in config.
    """
    if not settings.fred_api_key:
        logger.warning("FRED_API_KEY not set — skipping macro data")
        return {}

    ids = series_ids or list(SERIES.keys())
    results: dict[str, dict] = {}

    try:
        import fredapi  # type: ignore
        fred = fredapi.Fred(api_key=settings.fred_api_key)

        def _fetch(series_id: str) -> dict:
            try:
                series = fred.get_series_latest_release(series_id)
                if series.empty:
                    return {}
                latest_val = float(series.iloc[-1])
                latest_date = series.index[-1]
                return {
                    "value": latest_val,
                    "date": latest_date.to_pydatetime() if hasattr(latest_date, "to_pydatetime") else str(latest_date),
                    "description": SERIES.get(series_id, series_id),
                }
            except Exception as e:
                logger.warning("FRED series %s failed: %s", series_id, e)
                return {}

        for sid in ids:
            result = await asyncio.get_event_loop().run_in_executor(None, lambda s=sid: _fetch(s))
            if result:
                results[sid] = result

    except ImportError:
        logger.warning("fredapi not installed — skipping FRED data")
    except Exception as e:
        logger.error("FRED fetch error: %s", e)

    return results


async def fetch_yield_curve() -> dict:
    """Return yield curve spread (10Y - 2Y) as inversion indicator."""
    data = await fetch_macro_data(["DGS10", "DGS2"])
    ten = data.get("DGS10", {}).get("value")
    two = data.get("DGS2", {}).get("value")
    if ten is None or two is None:
        return {"spread": None, "inverted": None}
    spread = ten - two
    return {
        "spread": round(spread, 3),
        "inverted": spread < 0,
        "ten_year": ten,
        "two_year": two,
    }


async def fetch_vix() -> Optional[float]:
    """Return current VIX level."""
    data = await fetch_macro_data(["VIXCLS"])
    return data.get("VIXCLS", {}).get("value")
