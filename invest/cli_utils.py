"""Shared CLI utilities for invest-manager commands."""

import asyncio
import sys
from functools import wraps

import click
from rich.console import Console

from invest.db.engine import init_db

console = Console()


def coro(f):
    """Decorator: initialises DB then runs an async Click command via asyncio.run()."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        async def inner():
            try:
                await init_db()
                await f(*args, **kwargs)
            except click.Abort:
                raise
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {e}")
                sys.exit(1)

        return asyncio.run(inner())

    return wrapper
