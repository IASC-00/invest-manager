"""Rolling Z-score anomaly detector."""
import pandas as pd

from invest.config import settings
from invest.detection.models import AlertLevel, AnomalyResult

WINDOW = 20


def detect(symbol: str, df: pd.DataFrame) -> list[AnomalyResult]:
    """Flag if latest close deviates > threshold σ from 20-day rolling mean."""
    if df.empty or "Close" not in df.columns or len(df) < WINDOW + 1:
        return []

    close = df["Close"].dropna()
    rolling_mean = close.rolling(WINDOW).mean()
    rolling_std = close.rolling(WINDOW).std()

    latest_close = close.iloc[-1]
    mean = rolling_mean.iloc[-1]
    std = rolling_std.iloc[-1]

    if std == 0 or pd.isna(std):
        return []

    z = (latest_close - mean) / std
    threshold = settings.zscore_threshold

    if abs(z) <= threshold:
        return []

    direction = "above" if z > 0 else "below"
    score = min(abs(z) / (threshold * 2), 1.0)
    level = AlertLevel.CRITICAL if abs(z) > threshold * 1.5 else AlertLevel.WARNING

    return [
        AnomalyResult(
            symbol=symbol,
            detector="zscore",
            level=level,
            title=f"{symbol} price {abs(z):.1f}σ {direction} 20-day mean",
            detail={
                "z_score": round(float(z), 3),
                "current_price": round(float(latest_close), 4),
                "rolling_mean": round(float(mean), 4),
                "rolling_std": round(float(std), 4),
                "threshold": threshold,
            },
            score=score,
        )
    ]
