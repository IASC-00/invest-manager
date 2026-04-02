"""invest-manager CLI entry point.

Commands:
    invest portfolio  — show active positions with live prices and P&L
    invest add        — add a new position
    invest close      — close a position at a given price
    invest detect     — run z-score anomaly detection across all positions
    invest pulse      — show market benchmark snapshot
"""

import asyncio
import sys
from datetime import datetime

import click
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from invest.cli_utils import coro
from invest.db.engine import get_session
from invest.db.models import AssetType
from invest.data.fetcher import (
    fetch_all_prices,
    fetch_market_pulse,
    fetch_ohlcv_for_symbol,
)
from invest.detection.zscore import detect
from invest.portfolio.manager import (
    add_position,
    build_portfolio_with_prices,
    close_position,
    get_active_positions,
)
from invest.portfolio.schemas import PositionCreate

console = Console()

PULSE_SYMBOLS = ["SPY", "QQQ", "^VIX", "GLD", "BTC"]
DISPLAY_NAMES = {"^VIX": "VIX", "SPY": "SPY", "QQQ": "QQQ", "GLD": "GLD", "BTC": "BTC"}


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _fmt_price(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "[dim]—[/dim]"
    return f"${value:,.{decimals}f}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "[dim]—[/dim]"
    sign = "+" if value >= 0 else ""
    color = "green" if value >= 0 else "red"
    return f"[{color}]{sign}{value:.2f}%[/{color}]"


def _fmt_pnl(value: float | None) -> str:
    if value is None:
        return "[dim]—[/dim]"
    sign = "+" if value >= 0 else ""
    color = "green" if value >= 0 else "red"
    return f"[{color}]{sign}${value:,.2f}[/{color}]"


def _fmt_day_change(value: float | None) -> str:
    if value is None:
        return "[dim]—[/dim]"
    sign = "+" if value >= 0 else ""
    color = "green" if value >= 0 else "red"
    return f"[{color}]{sign}${value:,.2f}[/{color}]"


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
def cli():
    """invest-manager — personal portfolio tracker with anomaly detection."""
    pass


# ---------------------------------------------------------------------------
# invest portfolio
# ---------------------------------------------------------------------------


@cli.command(name="portfolio")
@coro
async def portfolio():
    """Show active positions with live prices and P&L."""
    async with get_session() as session:
        positions = await get_active_positions(session)
        if not positions:
            console.print(
                Panel(
                    "[yellow]No active positions.[/yellow]\n"
                    "Use [bold]invest add TICKER QUANTITY PRICE[/bold] to get started.",
                    title="Portfolio",
                    border_style="yellow",
                )
            )
            return

        price_map = await fetch_all_prices(positions)
        rows = await build_portfolio_with_prices(session, price_map)

    table = Table(box=box.SIMPLE_HEAVY, show_footer=False)
    table.add_column("Symbol", style="bold", no_wrap=True)
    table.add_column("Type", style="dim")
    table.add_column("Qty", justify="right")
    table.add_column("Avg Cost", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Mkt Value", justify="right")
    table.add_column("Unreal P&L", justify="right")
    table.add_column("P&L %", justify="right")
    table.add_column("Day Chg", justify="right")

    total_value = 0.0
    total_cost = 0.0

    for row in rows:
        p = row.position
        table.add_row(
            p.symbol,
            p.asset_type.value,
            f"{p.quantity:,.4f}".rstrip("0").rstrip("."),
            _fmt_price(p.avg_cost),
            _fmt_price(row.current_price),
            _fmt_price(row.market_value),
            _fmt_pnl(row.unrealized_pnl),
            _fmt_pct(row.unrealized_pnl_pct),
            _fmt_day_change(row.day_change),
        )
        if row.market_value is not None:
            total_value += row.market_value
        total_cost += row.cost_basis

    table.add_section()
    total_pnl = total_value - total_cost if total_value else None
    table.add_row(
        "[bold]TOTAL[/bold]",
        "",
        "",
        "",
        "",
        f"[bold]{_fmt_price(total_value if total_value else None)}[/bold]",
        f"[bold]{_fmt_pnl(total_pnl)}[/bold]",
        "",
        "",
    )

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    console.print(Panel(table, title=f"Portfolio — {date_str}", border_style="cyan"))


# ---------------------------------------------------------------------------
# invest add
# ---------------------------------------------------------------------------


@cli.command(name="add")
@click.argument("ticker")
@click.argument("quantity", type=float)
@click.argument("price", type=float)
@coro
async def add(ticker: str, quantity: float, price: float):
    """Add a new position.

    \b
    Examples:
        invest add AAPL 10 150.00
        invest add BTC 0.5 42000.00
    """
    asset_type_str = click.prompt(
        "Asset type",
        type=click.Choice([t.value for t in AssetType], case_sensitive=False),
        default="stock",
    )
    asset_type = AssetType(asset_type_str.lower())

    if asset_type == AssetType.OPTION:
        console.print(
            "[yellow]Options require additional fields (option_type, strike, expiry, underlying).\n"
            "Options support is not yet available in the CLI.[/yellow]"
        )
        sys.exit(1)

    data = PositionCreate(
        symbol=ticker.upper(),
        asset_type=asset_type,
        quantity=quantity,
        avg_cost=price,
    )

    async with get_session() as session:
        pos = await add_position(session, data)
        console.print(
            Panel(
                f"Added [bold]{pos.symbol}[/bold] — {quantity:,.4f}".rstrip("0").rstrip(
                    "."
                )
                + f" {asset_type.value} @ {_fmt_price(price)}",
                title="Position Added",
                border_style="green",
            )
        )


# ---------------------------------------------------------------------------
# invest close
# ---------------------------------------------------------------------------


@cli.command(name="close")
@click.argument("ticker")
@click.argument("price", type=float)
@coro
async def close(ticker: str, price: float):
    """Close a position at the given price.

    \b
    Examples:
        invest close AAPL 175.00
    """
    if price <= 0:
        console.print("[bold red]Price must be greater than zero.[/bold red]")
        sys.exit(1)

    async with get_session() as session:
        positions = await get_active_positions(session)
        matches = [p for p in positions if p.symbol == ticker.upper()]

        if not matches:
            console.print(
                f"[yellow]No active position found for {ticker.upper()}.[/yellow]"
            )
            return

        if len(matches) == 1:
            target = matches[0]
        else:
            table = Table(
                box=box.SIMPLE, title=f"Multiple positions for {ticker.upper()}"
            )
            table.add_column("ID", justify="right")
            table.add_column("Qty", justify="right")
            table.add_column("Avg Cost", justify="right")
            table.add_column("Opened", justify="right")
            for p in matches:
                table.add_row(
                    str(p.id),
                    f"{p.quantity:,.4f}",
                    _fmt_price(p.avg_cost),
                    p.opened_at.strftime("%Y-%m-%d"),
                )
            console.print(table)
            valid_ids = [p.id for p in matches]
            chosen_id = click.prompt("Select position ID", type=int)
            if chosen_id not in valid_ids:
                console.print("[red]Invalid ID.[/red]")
                sys.exit(1)
            target = next(p for p in matches if p.id == chosen_id)

        pos = await close_position(session, target.id, price)
        if pos is None:
            console.print("[red]Failed to close position.[/red]")
            return

        realized = (price - pos.avg_cost) * pos.quantity
        console.print(
            Panel(
                f"Closed [bold]{pos.symbol}[/bold] — "
                f"{pos.quantity:,.4f} {pos.asset_type.value} @ {_fmt_price(price)}\n"
                f"Realized P&L: {_fmt_pnl(realized)}",
                title="Position Closed",
                border_style="green" if realized >= 0 else "red",
            )
        )


# ---------------------------------------------------------------------------
# invest detect
# ---------------------------------------------------------------------------


@cli.command(name="detect")
@coro
async def detect_cmd():
    """Run z-score anomaly detection across all active positions."""
    async with get_session() as session:
        positions = await get_active_positions(session)

    if not positions:
        console.print("[yellow]No active positions to scan.[/yellow]")
        return

    console.print(f"[dim]Scanning {len(positions)} position(s) for anomalies...[/dim]")

    ohlcv_tasks = [fetch_ohlcv_for_symbol(p.symbol, p.asset_type) for p in positions]
    ohlcv_results = await asyncio.gather(*ohlcv_tasks, return_exceptions=True)

    alerts = []
    for pos, result in zip(positions, ohlcv_results):
        if isinstance(result, Exception) or result is None:
            console.print(f"[dim]  {pos.symbol}: fetch failed, skipping[/dim]")
            continue
        if result.empty:
            console.print(f"[dim]  {pos.symbol}: no data, skipping[/dim]")
            continue
        alerts.extend(detect(pos.symbol, result))

    if not alerts:
        console.print(
            Panel(
                f"[green]No anomalies detected across {len(positions)} position(s).[/green]",
                title="Anomaly Detection",
                border_style="green",
            )
        )
        return

    alerts.sort(
        key=lambda a: (
            0 if a.level.value == "CRITICAL" else 1,
            -abs(a.detail.get("z_score", 0)),
        ),
    )

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Symbol", style="bold", no_wrap=True)
    table.add_column("Level", no_wrap=True)
    table.add_column("Title")
    table.add_column("Z-Score", justify="right")
    table.add_column("Score", justify="right")

    for a in alerts:
        level_str = (
            "[bold red]CRITICAL[/bold red]"
            if a.level.value == "CRITICAL"
            else "[yellow]WARNING[/yellow]"
        )
        z = a.detail.get("z_score", 0)
        table.add_row(a.symbol, level_str, a.title, f"{z:+.2f}", f"{a.score:.2f}")

    console.print(
        Panel(table, title="Anomaly Detection Results", border_style="yellow")
    )


# ---------------------------------------------------------------------------
# invest pulse
# ---------------------------------------------------------------------------


@cli.command(name="pulse")
@coro
async def pulse():
    """Show market benchmark snapshot (SPY, QQQ, VIX, GLD, BTC)."""
    console.print("[dim]Fetching market pulse...[/dim]")
    data = await fetch_market_pulse()

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Ticker", style="bold", no_wrap=True)
    table.add_column("Price", justify="right")
    table.add_column("Prev Close", justify="right", style="dim")
    table.add_column("Day Change", justify="right")
    table.add_column("Day Chg %", justify="right")

    for sym in PULSE_SYMBOLS:
        info = data.get(sym, {})
        price = info.get("price")
        prev_close = info.get("prev_close")
        day_change = info.get("day_change")
        day_change_pct = info.get("day_change_pct")

        # VIX displayed without $ sign
        if sym == "^VIX":
            price_str = f"{price:.2f}" if price is not None else "[dim]—[/dim]"
            prev_str = f"{prev_close:.2f}" if prev_close is not None else "[dim]—[/dim]"
        else:
            price_str = _fmt_price(price)
            prev_str = _fmt_price(prev_close)

        table.add_row(
            DISPLAY_NAMES.get(sym, sym),
            price_str,
            prev_str,
            _fmt_day_change(day_change),
            _fmt_pct(day_change_pct),
        )

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    console.print(Panel(table, title=f"Market Pulse — {date_str}", border_style="cyan"))


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
