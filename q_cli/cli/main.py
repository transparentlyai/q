"""Main entry point for the q_cli package."""

import anthropic
import os
import sys
from q_cli import __version__

from q_cli.cli.args import setup_argparse
from q_cli.io.config import read_config_file, build_context
from q_cli.io.input import create_prompt_session, get_initial_question, confirm_context
from q_cli.io.output import setup_console
from q_cli.utils.constants import (
    DEFAULT_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_ALWAYS_APPROVED_COMMANDS,
    DEFAULT_ALWAYS_RESTRICTED_COMMANDS,
    DEFAULT_PROHIBITED_COMMANDS,
    DEBUG,
)
from q_cli.utils.helpers import sanitize_context
from q_cli.cli.conversation import run_conversation
from q_cli.utils.permissions import CommandPermissionManager
from q_cli.utils.prompts import get_system_prompt


def main() -> None:
    """Main entry point for the CLI."""
    parser = setup_argparse()

    # If no args provided (sys.argv has just the script name), go into interactive mode
    if len(sys.argv) == 1:
        # Set the interactive mode flag to ensure we proceed with interactive mode
        sys.argv.append("--interactive")

    args = parser.parse_args()

    # Handle the update command if specified
    if args.update:
        from q_cli.cli.args import update_command

        update_command()

    # Initialize console for output
    console = setup_console()

    # Check for updates and notify user if available
    from q_cli.utils.helpers import check_for_updates, is_newer_version

    update_available, latest_version = check_for_updates()

    # Debug version check information
    if os.environ.get("Q_DEBUG"):
        console.print(
            f"[dim]Current version: {__version__}, Latest version from GitHub: {latest_version or 'not found'}[/dim]"
        )
        if latest_version:
            is_newer = is_newer_version(latest_version, __version__)
            console.print(f"[dim]Is GitHub version newer: {is_newer}[/dim]")

    if update_available:
        msg = f"[dim]New version {latest_version} available. Run 'q --update' to update.[/dim]"
        console.print(msg)

    # Get API key and config vars from config file
    config_api_key, config_context, config_vars = read_config_file(console)

    # Use API key from args, config file, or environment variable (in that order)
    api_key = args.api_key or config_api_key or os.environ.get("ANTHROPIC_API_KEY")

    # Set model from args, config file, or default
    if not args.model:
        args.model = config_vars.get("MODEL", DEFAULT_MODEL)

    # Set max_tokens from config file or default
    args.max_tokens = int(config_vars.get("MAX_TOKENS", DEFAULT_MAX_TOKENS))

    if not api_key:
        console.print(
            "[bold red]Error: Anthropic API key not provided. Add to ~/.config/q.conf, set ANTHROPIC_API_KEY environment variable, or use --api-key[/bold red]"
        )
        sys.exit(1)

    # Initialize client with error handling
    try:
        client = anthropic.Anthropic(api_key=api_key)
    except Exception as e:
        console.print(
            f"[bold red]Error initializing Anthropic client: {str(e)}[/bold red]"
        )
        console.print("[yellow]Please check your API key and try again.[/yellow]")
        sys.exit(1)

    # Set up prompt session for input
    prompt_session = create_prompt_session(console)
    history = prompt_session.history

    # Check if file tree should be included from args or config
    include_file_tree = getattr(args, "file_tree", False)

    # Also check the config file - config vars are all uppercase
    if (
        not include_file_tree
        and config_vars.get("INCLUDE_FILE_TREE", "").lower() == "true"
    ):
        include_file_tree = True

    # Set the constant if needed
    if include_file_tree:
        # Import in local scope to avoid circular imports
        import q_cli.utils.constants as constants

        constants.INCLUDE_FILE_TREE = True

        if constants.DEBUG:
            console.print("[info]File tree will be included in context[/info]")

    # Build and sanitize context from config and files
    context, context_manager = build_context(args, config_context, console)
    sanitized_context = sanitize_context(context, console)

    # Set up system prompt with context if available
    include_command_execution = not getattr(args, "no_execute", False)
    base_system_prompt = get_system_prompt(
        include_command_execution=include_command_execution,
        context=None,  # We'll set context separately
    )

    # Set system prompt and add conversation context
    if sanitized_context:
        # Context is now managed by the ContextManager
        system_prompt = get_system_prompt(
            include_command_execution=include_command_execution,
            context=sanitized_context,
        )
    else:
        system_prompt = base_system_prompt

    # Make sure the context manager knows about the system prompt
    context_manager.set_system_prompt(system_prompt)

    # If confirm-context is specified, show the context and ask for confirmation
    if args.confirm_context and sanitized_context:
        if not confirm_context(prompt_session, system_prompt, console):
            console.print("Context rejected. Exiting.", style="info")
            sys.exit(0)

    # Set up permission manager
    permission_manager = CommandPermissionManager.from_config(config_vars)

    # Check if auto-approve flag is set
    auto_approve = getattr(args, "yes", False)

    # Always add default commands to the user-configured ones
    # This ensures defaults are always included while allowing user customization
    permission_manager.always_approved_commands.update(DEFAULT_ALWAYS_APPROVED_COMMANDS)
    permission_manager.always_restricted_commands.update(
        DEFAULT_ALWAYS_RESTRICTED_COMMANDS
    )
    permission_manager.prohibited_commands.update(DEFAULT_PROHIBITED_COMMANDS)

    # Get initial question from args, file, or prompt
    try:
        question = get_initial_question(args, prompt_session, history)
    except (KeyboardInterrupt, EOFError):
        sys.exit(0)

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
        sys.exit(0)

    # Run the conversation with improved error handling
    try:
        run_conversation(
            client,
            system_prompt,
            args,
            prompt_session,
            console,
            question,
            permission_manager,
            context_manager=context_manager,
            auto_approve=auto_approve,
        )
    except (KeyboardInterrupt, EOFError):
        # Handle Ctrl+C or Ctrl+D gracefully at the top level
        console.print("\n[yellow]Operation interrupted. Exiting.[/yellow]")
        sys.exit(0)
    except Exception as e:
        # Catch any unexpected exceptions that weren't handled in run_conversation
        console.print(f"\n[bold red]Unexpected error: {str(e)}[/bold red]")
        if DEBUG:
            import traceback

            console.print(f"[red]{traceback.format_exc()}[/red]")
        console.print(
            "[yellow]The application encountered an error and must exit.[/yellow]"
        )
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Last chance to catch any uncaught exceptions
        # Import console here since we might not have it initialized
        from rich.console import Console

        console = Console()
        console.print(f"\n[bold red]Fatal error: {str(e)}[/bold red]")
        if os.environ.get("Q_DEBUG", "false").lower() == "true":
            import traceback

            console.print(f"[red]{traceback.format_exc()}[/red]")
        console.print(
            "[yellow]The application encountered a fatal error and must exit.[/yellow]"
        )
        sys.exit(1)
