from __future__ import annotations

import typer
from rich.console import Console

from ..config import init_config
from ..db import init_db

app = typer.Typer(
    name="selfheal",
    help="AI-driven life manager. It tells you what to do, when, and in what order.",
    no_args_is_help=False,
)
console = Console()

def _ensure_init():
    init_config()
    init_db()
