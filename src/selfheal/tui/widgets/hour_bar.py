from __future__ import annotations

from textual.widgets import Static


class HourBar(Static):
    def __init__(self, blocks: list[dict] | None = None, *, id: str | None = None):
        super().__init__(id=id)
        self.blocks = blocks or []

    def update_blocks(self, blocks: list[dict]):
        self.blocks = blocks
        self.refresh()

    def render(self) -> str:
        if not self.blocks:
            return "[dim]No hour data available[/]"

        parts: list[str] = []
        for block in self.blocks:
            status = block.get("status", "free")
            if status == "committed":
                parts.append("[red]█[/]")
            elif status == "peak":
                parts.append("[green]█[/]")
            elif status == "low":
                parts.append("[yellow]█[/]")
            elif status == "free":
                parts.append("[cyan]█[/]")
            else:
                parts.append("[dim]█[/]")

        return (
            "[bold]Hour Burn-down[/]\n"
            + "".join(parts)
            + "\n"
            + "[dim]Green=Peak Red=Committed Yellow=Low Cyan=Free[/]"
        )
