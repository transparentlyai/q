"""Main entry point for the q_cli package."""

import anthropic
import littlellm
from q_cli.utils.client import LLMClient
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

    # Handle the recover command if specified
    if args.recover:
        from q_cli.utils.session.manager import recover_session

        # Initialize necessary components for recovery
        # Get API key and config vars from config file
        config_api_key, _, config_vars = read_config_file(console)

        # Get provider from args, config file, or default
        provider = args.provider or config_vars.get("PROVIDER", DEFAULT_PROVIDER)
        
        # Get API key based on provider
        if args.api_key:
            # Use API key from args
            api_key = args.api_key
        elif provider.lower() == "anthropic":
            api_key = config_vars.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        elif provider.lower() == "vertexai":
            api_key = config_vars.get("VERTEXAI_API_KEY") or os.environ.get("VERTEXAI_API_KEY")
        elif provider.lower() == "groq":
            api_key = config_vars.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY")
        else:
            # Fallback to generic API key or anthropic key for backward compatibility
            api_key = config_api_key or os.environ.get("API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        
        # Set model based on provider if not explicitly specified
        if not args.model:
            if provider.lower() == "anthropic":
                args.model = config_vars.get("MODEL", ANTHROPIC_DEFAULT_MODEL)
            elif provider.lower() == "vertexai":
                args.model = config_vars.get("MODEL", VERTEXAI_DEFAULT_MODEL)
            elif provider.lower() == "groq":
                args.model = config_vars.get("MODEL", GROQ_DEFAULT_MODEL)
            else:
                args.model = config_vars.get("MODEL", DEFAULT_MODEL)

        # Force interactive mode when recovering
        args.no_interactive = False
        args.interactive = True

        # Check for API key
        if not api_key:
            console.print(
                f"[bold red]Error: API key for {provider} not provided. Add to ~/.config/q.conf, set {provider.upper()}_API_KEY environment variable, or use --api-key[/bold red]"
            )
            sys.exit(1)

        try:
            # Initialize LLM client wrapper
            client = LLMClient(api_key=api_key, model=args.model, provider=provider)

            # Set up prompt session for input
            prompt_session = create_prompt_session(console)

            # Set up permission manager
            permission_manager = CommandPermissionManager.from_config(config_vars)

            # Always add default commands
            permission_manager.always_approved_commands.update(
                DEFAULT_ALWAYS_APPROVED_COMMANDS
            )
            permission_manager.always_restricted_commands.update(
                DEFAULT_ALWAYS_RESTRICTED_COMMANDS
            )
            permission_manager.prohibited_commands.update(DEFAULT_PROHIBITED_COMMANDS)

            # Attempt to recover the session
            if recover_session(
                client, args, prompt_session, console, permission_manager
            ):
                # If recovery was successful and conversation started, exit
                sys.exit(0)
            # Otherwise fall through to normal startup

        except Exception as e:
            console.print(
                f"[bold red]Error during session recovery: {str(e)}[/bold red]"
            )
            if DEBUG:
                import traceback

                console.print(f"[red]{traceback.format_exc()}[/red]")
            # Continue with normal startup

    # Console already initialized above for recovery command
    # Skip re-initializing console here

    # Check for updates and notify user if available
    from q_cli.utils.helpers import check_for_updates, is_newer_version

    update_available, latest_version = check_for_updates(console)

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

    # Get provider from args, config file, or default
    provider = args.provider or config_vars.get("PROVIDER", DEFAULT_PROVIDER)
    
    # Get API key based on provider
    if args.api_key:
        # Use API key from args
        api_key = args.api_key
    elif provider.lower() == "anthropic":
        api_key = config_vars.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    elif provider.lower() == "vertexai":
        api_key = config_vars.get("VERTEXAI_API_KEY") or os.environ.get("VERTEXAI_API_KEY")
    elif provider.lower() == "groq":
        api_key = config_vars.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY")
    else:
        # Fallback to generic API key or anthropic key for backward compatibility
        api_key = config_api_key or os.environ.get("API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    
    # Set model based on provider if not explicitly specified
    if not args.model:
        if provider.lower() == "anthropic":
            args.model = config_vars.get("MODEL", ANTHROPIC_DEFAULT_MODEL)
        elif provider.lower() == "vertexai":
            args.model = config_vars.get("MODEL", VERTEXAI_DEFAULT_MODEL)
        elif provider.lower() == "groq":
            args.model = config_vars.get("MODEL", GROQ_DEFAULT_MODEL)
        else:
            args.model = config_vars.get("MODEL", DEFAULT_MODEL)
    
    # Set max_tokens from config file or default
    args.max_tokens = int(config_vars.get("MAX_TOKENS", DEFAULT_MAX_TOKENS))
    
    if not api_key:
        console.print(
            f"[bold red]Error: API key for {provider} not provided. Add to ~/.config/q.conf, set {provider.upper()}_API_KEY environment variable, or use --api-key[/bold red]"
        )
        sys.exit(1)
    
    # Initialize client with error handling
    try:
        # Initialize our LLM client wrapper
        client = LLMClient(api_key=api_key, model=args.model, provider=provider)
        
        if DEBUG:
            console.print(f"[dim]Using provider: {provider}, model: {args.model}[/dim]")
    
    except Exception as e:
        console.print(
            f"[bold red]Error initializing LLM client with provider {provider}: {str(e)}[/bold red]"
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
        # Set the constant directly
        from q_cli.utils.constants import INCLUDE_FILE_TREE

        INCLUDE_FILE_TREE = True

        if DEBUG:
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

    # Initialize session manager for saving conversation state
    from q_cli.utils.session.manager import SessionManager

    session_manager = SessionManager(console)

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
            session_manager=session_manager,
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
