"""P&L and cost basis calculations (FIFO)."""
from dataclasses import dataclass

from invest.db.models import Transaction, TransactionType


@dataclass
class PnLResult:
    cost_basis: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    realized_pnl: float


def fifo_cost_basis(transactions: list[Transaction]) -> float:
    """
    Compute average cost basis using FIFO matching.
    Returns the cost basis of remaining open quantity.
    """
    buys: list[tuple[float, float]] = []  # (qty, price)
    realized_pnl = 0.0

    for tx in sorted(transactions, key=lambda t: t.executed_at):
        if tx.tx_type == TransactionType.BUY:
            buys.append((tx.quantity, tx.price))
        elif tx.tx_type == TransactionType.SELL:
            remaining_sell = tx.quantity
            while remaining_sell > 0 and buys:
                qty, cost = buys[0]
                if qty <= remaining_sell:
                    realized_pnl += qty * (tx.price - cost)
                    remaining_sell -= qty
                    buys.pop(0)
                else:
                    realized_pnl += remaining_sell * (tx.price - cost)
                    buys[0] = (qty - remaining_sell, cost)
                    remaining_sell = 0

    if not buys:
        return 0.0

    total_qty = sum(q for q, _ in buys)
    total_cost = sum(q * p for q, p in buys)
    return total_cost / total_qty if total_qty > 0 else 0.0


def compute_pnl(
    quantity: float,
    avg_cost: float,
    current_price: float | None,
    transactions: list[Transaction],
) -> PnLResult:
    """Compute unrealized and realized P&L for a position."""
    cost_basis = fifo_cost_basis(transactions) if transactions else avg_cost
    realized_pnl = _compute_realized(transactions)

    if current_price is None:
        return PnLResult(
            cost_basis=cost_basis,
            market_value=quantity * cost_basis,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
            realized_pnl=realized_pnl,
        )

    market_value = quantity * current_price
    total_cost = quantity * cost_basis
    unrealized_pnl = market_value - total_cost
    unrealized_pnl_pct = (unrealized_pnl / total_cost * 100) if total_cost != 0 else 0.0

    return PnLResult(
        cost_basis=cost_basis,
        market_value=market_value,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=unrealized_pnl_pct,
        realized_pnl=realized_pnl,
    )


def _compute_realized(transactions: list[Transaction]) -> float:
    """Compute realized P&L from closed FIFO lots."""
    buys: list[tuple[float, float]] = []
    realized = 0.0
    for tx in sorted(transactions, key=lambda t: t.executed_at):
        if tx.tx_type == TransactionType.BUY:
            buys.append((tx.quantity, tx.price))
        elif tx.tx_type == TransactionType.SELL:
            remaining = tx.quantity
            while remaining > 0 and buys:
                qty, cost = buys[0]
                matched = min(qty, remaining)
                realized += matched * (tx.price - cost)
                remaining -= matched
                if matched >= qty:
                    buys.pop(0)
                else:
                    buys[0] = (qty - matched, cost)
    return realized
