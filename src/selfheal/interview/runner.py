from __future__ import annotations

import re
from typing import Any

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ..config import save_life_model, load_life_model
from ..llm import get_llm_with_fallback
from ..obsidian import save_interview_to_obsidian
from .prompts import SYSTEM_PROMPT, FOLLOW_UP_PROMPT, REGENERATE_PROMPT

console = Console()


def run_interview(regenerate: bool = False) -> dict[str, Any] | None:
    llm = get_llm_with_fallback()
    messages: list[dict[str, str]] = []

    if regenerate:
        current = load_life_model()
        if current:
            current_yaml = yaml.dump(current, default_flow_style=False)
            system_msg = REGENERATE_PROMPT.format(current_model=current_yaml)
        else:
            system_msg = SYSTEM_PROMPT
    else:
        system_msg = SYSTEM_PROMPT

    messages.append({"role": "system", "content": system_msg})

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

    while True:
        try:
            if not messages or messages[-1]["role"] == "user":
                response = llm.chat(messages, temperature=0.7)
                assistant_msg = response.content
                messages.append({"role": "assistant", "content": assistant_msg})

                if "[INTERVIEW_COMPLETE]" in assistant_msg:
                    model = _extract_yaml(assistant_msg)
                    if model:
                        save_life_model(model)
                        save_interview_to_obsidian(messages, model)
                        _print_summary(model)
                        return model
                    else:
                        console.print("[yellow]Could not parse life model. Let me ask a bit more...[/]")
                        messages.append({"role": "user", "content": "Please provide the YAML life model again, making sure it is valid YAML."})
                        continue

                _print_assistant(assistant_msg)

            user_input = console.input("[bold green]You:[/] ").strip()
            if user_input.lower() in ("quit", "exit", "q"):
                console.print("[yellow]Interview cancelled.[/]")
                return None
            if not user_input:
                continue

            messages.append({"role": "user", "content": user_input})

            if len(messages) > 30:
                messages = [_compress_history(messages)]

        except KeyboardInterrupt:
            console.print("\n[yellow]Interview stopped.[/]")
            return None


def _print_assistant(text: str):
    clean = text.replace("[INTERVIEW_COMPLETE]", "").strip()
    if clean:
        console.print()
        console.print(Panel(clean, title="[bold]SelfHeal[/]", border_style="blue"))
        console.print()


def _extract_yaml(text: str) -> dict[str, Any] | None:
    yaml_match = re.search(r"```yaml\s*\n(.*?)```", text, re.DOTALL)
    if yaml_match:
        try:
            return yaml.safe_load(yaml_match.group(1))
        except yaml.YAMLError:
            pass

    yaml_match = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if yaml_match:
        try:
            return yaml.safe_load(yaml_match.group(1))
        except yaml.YAMLError:
            pass

    return None


def _compress_history(messages: list[dict[str, str]]) -> dict[str, str]:
    history_text = ""
    for m in messages:
        role = m["role"]
        content = m["content"][:300]
        history_text += f"{role}: {content}\n"
    return {
        "role": "system",
        "content": FOLLOW_UP_PROMPT.format(history=history_text),
    }


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
