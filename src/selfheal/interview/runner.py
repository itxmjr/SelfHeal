from __future__ import annotations

from typing import Any
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .session import InterviewSession

console = Console()

def run_interview(regenerate: bool = False) -> dict[str, Any] | None:
    session = InterviewSession(regenerate=regenerate)

    console.print()
    console.print(Panel(
        Text.from_markup(
            "[bold cyan]SelfHeal Interview[/]\n\n"
            "This takes about 15 minutes. I'll learn about your life, commitments, and goals.\n"
            "Then I'll build a Life Model that drives your daily schedule automatically.\n\n"
            "[dim]Type your answers naturally. Type 'quit' to stop.[/]"
        ),
        border_style="cyan",
    ))
    console.print()

    # Initial question
    assistant_msg = session.get_initial_question()
    _print_assistant(assistant_msg)

    while not session.is_complete:
        try:
            user_input = console.input("[bold green]You:[/] ").strip()
            if user_input.lower() in ("quit", "exit", "q"):
                console.print("[yellow]Interview cancelled.[/]")
                return None
            if not user_input:
                continue

            resp = session.respond(user_input)
            
            if resp == "INTERVIEW_COMPLETE":
                _print_summary(session.model)
                return session.model
            
            _print_assistant(resp)

        except KeyboardInterrupt:
            console.print("\n[yellow]Interview stopped.[/]")
            return None

def _print_assistant(text: str):
    if text:
        console.print()
        console.print(Panel(text, title="[bold]SelfHeal[/]", border_style="blue"))
        console.print()

def _print_summary(model: dict[str, Any]):
    console.print()
    sleep = model.get("sleep", {})
    commitments = model.get("commitments", [])
    goals = model.get("goals", [])
    energy = model.get("energy", {})

    summary_lines = [
        f"[bold]Sleep:[/] {sleep.get('wake', '?')} - {sleep.get('bed', '?')} ({sleep.get('need_hours', '?')}h)",
        f"[bold]Commitments:[/] {len(commitments)}",
    ]
    for c in commitments:
        summary_lines.append(f"  - {c.get('name', '?')}: {c.get('hours', '?')} ({c.get('days', '?')})")

    summary_lines.append(f"[bold]Goals:[/] {len(goals)}")
    for g in goals:
        summary_lines.append(f"  - {g.get('name', '?')} [{g.get('priority', '?')}] {g.get('frequency', '?')}")

    if energy:
        summary_lines.append(f"[bold]Peak energy:[/] {energy.get('peak', '?')}")
        summary_lines.append(f"[bold]Low energy:[/] {energy.get('low', '?')}")

    console.print(Panel(
        "\n".join(summary_lines),
        title="[bold green]Life Model Saved[/]",
        border_style="green",
    ))
    console.print("[dim]Run 'selfheal today' to see your AI-generated schedule.[/]")
    console.print()
