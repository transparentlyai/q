"""Dry run functionality for q_cli."""

import sys
from typing import Any, Dict, List
from rich.console import Console


def handle_dry_run(
    args: Any,
    question: str,
    system_prompt: str,
    console: Console
) -> bool:
    """Handle dry run mode if enabled.

    Args:
        args: Command line arguments
        question: Initial question from user
        system_prompt: System prompt including context
        console: Console for output

    Returns:
        True if dry run was handled and program should exit, False otherwise
    """
    # If dry-run is enabled, print the message that would be sent to Claude and exit
    if getattr(args, "dry_run", False):
        # Initialize conversation with the initial question
        conversation = []
        if question.strip():
            conversation.append({"role": "user", "content": question})

        # Create a formatted representation of the message
        dry_run_output = (
            "\n===== DRY RUN MODE =====\n\n"
            f"[bold blue]Model:[/bold blue] {args.model}\n"
            f"[bold blue]Max tokens:[/bold blue] {args.max_tokens}\n"
            f"[bold blue]Temperature:[/bold blue] 0\n\n"
            f"[bold green]System prompt:[/bold green]\n{system_prompt}\n\n"
        )

        if conversation:
            dry_run_output += f"[bold yellow]User message:[/bold yellow]\n{question}\n"
        else:
            dry_run_output += "[bold yellow]No initial user message[/bold yellow]\n"

        console.print(dry_run_output)
        return True

    return False
