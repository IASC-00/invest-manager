"""Shared models for anomaly detection results."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AnomalyResult:
    symbol: str
    detector: str
    level: AlertLevel
    title: str
    detail: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0           # 0.0 – 1.0 severity
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_db_dict(self) -> dict:
        import json
        return {
            "symbol": self.symbol,
            "detector": self.detector,
            "level": self.level.value,
            "title": self.title,
            "detail_json": json.dumps(self.detail),
            "ai_score": self.score,
        }
