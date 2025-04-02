"""Update and version check functionality for q_cli."""

import sys
import subprocess
from threading import Thread
from typing import Any
from rich.console import Console

from q_cli import __version__
from q_cli.utils.constants import get_debug
from q_cli.utils.helpers import check_for_updates, is_newer_version


def handle_update_command(args: Any) -> bool:
    """Handle the update command if specified.

    Args:
        args: Command line arguments

    Returns:
        True if update was handled and program should exit, False otherwise
    """
    if args.update:
        update_command()
        return True
    return False


def update_command():
    """Update q to the latest version from GitHub."""
    try:
        print("Updating q to the latest version...")
        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "git+https://github.com/transparentlyai/q.git",
            ]
        )
        print("Update completed successfully!")
    except subprocess.CalledProcessError as e:
        print(f"Error updating q: {e}")
    sys.exit(0)


def check_updates_async(console: Console) -> None:
    """Check for updates asynchronously without blocking startup.

    Args:
        console: Console for output
    """
    def _check_update():
        update_available, latest_version = check_for_updates(console)
        if update_available:
            msg = f"[dim]New version {latest_version} available. Run 'q --update' to update.[/dim]"
            console.print(msg)

        # Debug version check information
        if get_debug():
            console.print(
                f"[dim]Current version: {__version__}, "
                f"Latest version from GitHub: {latest_version or 'not found'}[/dim]"
            )
            if latest_version:
                is_newer = is_newer_version(latest_version, __version__)
                console.print(f"[dim]Is GitHub version newer: {is_newer}[/dim]")

    # Run in background thread to avoid blocking startup
    update_thread = Thread(target=_check_update)
    update_thread.daemon = True
    update_thread.start()
