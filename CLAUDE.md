# Invest Manager CLI — Claude Context

## Purpose
Personal CLI investment manager with anomaly detection and AI insights.

## Stack
Python 3.11+, Click, Rich, Pandas, yfinance, pydantic, SQLAlchemy, Anthropic SDK

## Status
Phase 1 MVP complete. All 5 CLI commands working.

## Commands
```bash
invest portfolio          # show positions with live prices + P&L
invest add TICKER QTY PRICE  # add position (prompts for asset type)
invest close TICKER PRICE    # close position, record realized P&L
invest detect             # z-score anomaly scan across all positions
invest pulse              # market snapshot: SPY, QQQ, VIX, GLD, BTC
```

## Structure
- `pyproject.toml` — dependencies, entry point: `invest = "invest.main:cli"`
- `invest/main.py` — CLI entry point (Click + Rich)
- `invest/db/` — SQLAlchemy models + async engine (aiosqlite)
- `invest/data/` — price fetchers: yfinance, CoinGecko, FRED + TTL cache
- `invest/portfolio/` — CRUD, FIFO P&L calculator, Pydantic schemas
- `invest/detection/zscore.py` — rolling z-score anomaly detector
- `invest/ai/` — scaffolded, not yet implemented
- `invest/ui/` — Textual TUI, scaffolded, not yet implemented
- DB stored at: `~/.invest-manager/invest.db`

## Next phases
- Phase 2: more detectors (volume spike, options flow)
- Phase 3: AI commentary via Anthropic SDK (`invest ai TICKER`)
- Phase 4: Textual TUI dashboard

## Resume
Read this file, then check TODO in memory files for next task.
