from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API keys
    anthropic_api_key: str = ""
    fred_api_key: str = ""
    litellm_master_key: str = "sk-invest"

    # Database
    db_path: Path = Path.home() / ".invest-manager" / "invest.db"

    # LiteLLM proxy
    litellm_base_url: str = "http://localhost:4000"

    # Detection thresholds
    zscore_threshold: float = 2.5
    volume_spike_ratio: float = 3.0
    crypto_spread_pct: float = 1.5
    ai_escalation_score: float = 7.0

    # Alert deduplication
    alert_dedup_hours: int = 4

    # Cache TTLs (seconds)
    cache_ttl_ohlcv: int = 900        # 15 min
    cache_ttl_options: int = 300      # 5 min
    cache_ttl_crypto: int = 120       # 2 min
    cache_ttl_macro: int = 14400      # 4 hours

    def ensure_db_dir(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
