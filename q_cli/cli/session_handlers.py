"""Session management handlers for q_cli.

This module provides functions for handling session operations like
recovery, saving, and managing conversational state.
"""

import sys
import traceback
from typing import Any, Dict, Optional, Tuple
from rich.console import Console

from q_cli.utils.constants import get_debug
from q_cli.utils.permissions import CommandPermissionManager
from q_cli.io.input import create_prompt_session


def handle_recover_command(args: Any, console: Console) -> bool:
    """Handle the recover command if specified.

    Args:
        args: Command line arguments
        console: Console for output

    Returns:
        True if recovery was handled and program should exit, False otherwise
    """
    if not args.recover:
        return False

    from q_cli.utils.session.manager import recover_session
    from q_cli.config.manager import ConfigManager
    from q_cli.cli.client_init import initialize_llm_client

    try:
        # Initialize config manager
        config_manager = ConfigManager(console)

        # Get configuration for recovery
        config_manager.load_config()

        # Get provider settings
        provider, api_key, provider_kwargs = config_manager.get_provider_settings(args)

        # Configure model settings
        config_manager.configure_model_settings(args, provider)

        # Check for API key
        if not api_key:
            console.print(
                f"[bold red]Error: API key for {provider} not provided. Add to ~/.config/q.conf, "
                f"set {provider.upper()}_API_KEY environment variable, or use --api-key[/bold red]"
            )
            sys.exit(1)

        # Save provider_kwargs to args for later use
        args.provider_kwargs = provider_kwargs

        # Initialize LLM client wrapper
        client = initialize_llm_client(
            api_key=api_key,
            args=args,
            provider=provider,
            console=console
        )

        # Set up prompt session for input
        prompt_session = create_prompt_session(console)

        # Set up permission manager
        permission_manager = setup_permission_manager(config_manager.config_vars, args, console)

        # Attempt to recover the session
        if recover_session(
            client, args, prompt_session, console, permission_manager
        ):
            # If recovery was successful and conversation started, exit
            return True
        # Otherwise fall through to normal startup
        return False

    except Exception as e:
        console.print(
            f"[bold red]Error during session recovery: {str(e)}[/bold red]"
        )
        if get_debug():
            console.print(f"[red]{traceback.format_exc()}[/red]")
        # Continue with normal startup
        return False


def initialize_session_manager(args: Any, console: Console):
    """Initialize session manager if needed.

    Args:
        args: Command line arguments
        console: Console for output

    Returns:
        Session manager or None
    """
    session_manager = None
    if not getattr(args, "no_save", False):
        from q_cli.utils.session.manager import SessionManager
        session_manager = SessionManager(console)
    return session_manager


def setup_permission_manager(
    config_vars: Dict[str, Any],
    args: Any,
    console: Console
) -> Tuple[CommandPermissionManager, bool]:
    """Set up permission manager and auto-approve settings.

    Args:
        config_vars: Config variables
        args: Command line arguments
        console: Console for output

    Returns:
        Tuple containing:
        - Permission manager
        - Auto-approve flag
    """
    from q_cli.config.commands import (
        DEFAULT_ALWAYS_APPROVED_COMMANDS,
        DEFAULT_ALWAYS_RESTRICTED_COMMANDS,
        DEFAULT_PROHIBITED_COMMANDS
    )

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

    return permission_manager, auto_approve
