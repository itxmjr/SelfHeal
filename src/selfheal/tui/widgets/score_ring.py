from __future__ import annotations

from textual.widgets import Static


class ScoreRing(Static):
    def __init__(self, score: float = 0.0, *, id: str | None = None):
        super().__init__(id=id)
        self.score = float(score)

    def update_score(self, score: float):
        self.score = max(0.0, min(100.0, float(score)))
        self.refresh()

    def render(self) -> str:
        score = int(round(self.score))
        filled = min(10, max(0, score // 10))
        bar = "●" * filled + "○" * (10 - filled)

        if score >= 70:
            color = "green"
            mood = "On Track"
        elif score >= 40:
            color = "yellow"
            mood = "Recovering"
        else:
            color = "red"
            mood = "Needs Focus"

        return (
            f"[bold {color}]Today Score[/]\n"
            f"[bold {color}]{score}/100[/]\n"
            f"[{color}]{bar}[/]\n"
            f"[dim]{mood}[/]"
        )
