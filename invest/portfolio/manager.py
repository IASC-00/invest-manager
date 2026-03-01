"""CRUD operations for positions and transactions."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from invest.db.models import AssetType, Position, Transaction, TransactionType
from invest.portfolio.calculator import compute_pnl, fifo_cost_basis
from invest.portfolio.schemas import PositionCreate, PositionWithPnL, TransactionCreate


async def add_position(session: AsyncSession, data: PositionCreate) -> Position:
    """Create a new position and record the initial buy transaction."""
    pos = Position(
        symbol=data.symbol.upper(),
        asset_type=data.asset_type,
        quantity=data.quantity,
        avg_cost=data.avg_cost,
        currency=data.currency,
        notes=data.notes,
        option_type=data.option_type,
        strike=data.strike,
        expiry=data.expiry,
        underlying=data.underlying,
    )
    session.add(pos)
    await session.flush()  # get pos.id

    tx = Transaction(
        position_id=pos.id,
        tx_type=TransactionType.BUY,
        quantity=data.quantity,
        price=data.avg_cost,
    )
    session.add(tx)
    return pos


async def get_active_positions(session: AsyncSession) -> list[Position]:
    """Return all active positions with transactions eagerly loaded."""
    result = await session.execute(
        select(Position)
        .where(Position.is_active == True)  # noqa: E712
        .options(selectinload(Position.transactions))
        .order_by(Position.asset_type, Position.symbol)
    )
    return list(result.scalars().all())


async def get_position_by_id(session: AsyncSession, position_id: int) -> Position | None:
    result = await session.execute(
        select(Position)
        .where(Position.id == position_id)
        .options(selectinload(Position.transactions))
    )
    return result.scalar_one_or_none()


async def close_position(session: AsyncSession, position_id: int, price: float) -> Position | None:
    pos = await get_position_by_id(session, position_id)
    if pos is None:
        return None
    tx = Transaction(
        position_id=pos.id,
        tx_type=TransactionType.SELL,
        quantity=pos.quantity,
        price=price,
    )
    session.add(tx)
    pos.is_active = False
    return pos


async def build_portfolio_with_prices(
    session: AsyncSession,
    price_map: dict[str, dict],
) -> list[PositionWithPnL]:
    """
    price_map: {symbol: {"price": float, "prev_close": float|None}}
    Returns enriched positions sorted by market value descending.
    """
    positions = await get_active_positions(session)
    results: list[PositionWithPnL] = []

    for pos in positions:
        info = price_map.get(pos.symbol, {})
        current_price = info.get("price")
        prev_close = info.get("prev_close")

        pnl = compute_pnl(pos.quantity, pos.avg_cost, current_price, pos.transactions)

        day_change = None
        day_change_pct = None
        if current_price is not None and prev_close is not None and prev_close != 0:
            day_change = current_price - prev_close
            day_change_pct = day_change / prev_close * 100

        results.append(
            PositionWithPnL(
                position=pos,
                current_price=current_price,
                market_value=pnl.market_value,
                cost_basis=pnl.cost_basis,
                unrealized_pnl=pnl.unrealized_pnl,
                unrealized_pnl_pct=pnl.unrealized_pnl_pct,
                day_change=day_change,
                day_change_pct=day_change_pct,
            )
        )

    results.sort(key=lambda r: r.market_value or 0.0, reverse=True)
    return results
