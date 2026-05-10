from __future__ import annotations

import os

import typer
from rich.table import Table

from .core import console, _ensure_init
from ..daemon import (
    DaemonServer,
    daemon_get_status,
    daemon_stop,
    is_daemon_running,
)

daemon_app = typer.Typer(name="daemon", help="Background daemon management.")

@daemon_app.command(name="start")
def daemon_start():
    """Start the background daemon (forked process). Use 'daemon serve' for systemd."""
    _ensure_init()
    if is_daemon_running():
        status = daemon_get_status()
        console.print(f"[green]Daemon already running (PID {status.get('pid', '?')})[/]")
        return

    # Double fork to properly daemonize
    try:
        pid = os.fork()
        if pid > 0:
            # First parent
            os.waitpid(pid, 0)
            if is_daemon_running():
                status = daemon_get_status()
                console.print(f"[green]Daemon started (PID {status.get('pid', '?')})[/]")
            else:
                console.print("[red]Daemon failed to start.[/]")
            return
    except OSError as e:
        console.print(f"[red]Fork #1 failed: {e}[/]")
        raise typer.Exit(1)

    # First child
    os.setsid()
    try:
        pid = os.fork()
        if pid > 0:
            # Second parent
            os._exit(0)
    except OSError as e:
        console.print(f"[red]Fork #2 failed: {e}[/]")
        os._exit(1)

    # Second child - the actual daemon
    os.chdir("/")
    os.umask(0)

    # Redirect standard file descriptors
    import sys
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(os.devnull, 'w')
    sys.stdin = open(os.devnull, 'r')

    srv = DaemonServer()
    try:
        srv.start()
    finally:
        os._exit(0)

@daemon_app.command(name="serve")
def daemon_serve():
    """Run the daemon in foreground (for systemd). Blocks forever."""
    _ensure_init()
    console.print("[cyan]Starting SelfHeal daemon (foreground)...[/]")
    srv = DaemonServer()
    srv.start()

@daemon_app.command(name="stop")
def daemon_stop_cmd():
    """Stop the background daemon."""
    _ensure_init()
    if not is_daemon_running():
        console.print("[yellow]Daemon is not running.[/]")
        return

    if daemon_stop():
        console.print("[green]Daemon stopped.[/]")
    else:
        console.print("[red]Failed to stop daemon — may need to kill manually.[/]")

@daemon_app.command(name="status")
def daemon_status():
    """Show daemon running status."""
    _ensure_init()
    if not is_daemon_running():
        console.print("[yellow]Daemon is not running.[/]")
        console.print("Start with: [bold cyan]selfheal daemon start[/]")
        return

    status = daemon_get_status()
    table = Table(show_header=False, box=None, title="Daemon Status")
    table.add_column("Property", style="bold")
    table.add_column("Value")
    table.add_row("PID", str(status.get("pid", "?")))
    table.add_row("API URL", "http://127.0.0.1:8282")
    table.add_row("Started at", str(status.get("uptime", "?")))
    console.print(table)

@daemon_app.command(name="restart")
def daemon_restart():
    """Stop and restart the daemon."""
    daemon_stop_cmd()
    daemon_start()

@daemon_app.command(name="install")
def daemon_install():
    """Install systemd user service for the daemon."""
    import shutil
    import subprocess
    import sys
    from importlib.resources import files
    from pathlib import Path

    user_systemd_dir = Path.home() / ".config" / "systemd" / "user"
    user_systemd_dir.mkdir(parents=True, exist_ok=True)
    
    dest_service = user_systemd_dir / "selfheal-daemon.service"
    dest_target = user_systemd_dir / "selfheal.target"

    executable = shutil.which("selfheal") or str(Path(sys.executable).with_name("selfheal"))
    resource_root = files("selfheal.systemd")
    service_text = resource_root.joinpath("selfheal-daemon.service").read_text()
    service_text = service_text.replace("__SELFHEAL_EXECUTABLE__", executable)
    dest_service.write_text(service_text)
    dest_target.write_text(resource_root.joinpath("selfheal.target").read_text())

    console.print(f"[green]Copied service files to {user_systemd_dir}[/]")
    console.print("Enabling and starting service...")
    
    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "selfheal-daemon.service"], check=True)
        subprocess.run(["systemctl", "--user", "start", "selfheal-daemon.service"], check=True)
        console.print("[bold green]SelfHeal daemon installed and started via systemd![/]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Failed to enable/start service: {e}[/]")
