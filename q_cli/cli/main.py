"""Main entry point for the q_cli package."""

import os
import sys
from typing import Tuple, Dict, Any, Optional, List
from rich.console import Console
from q_cli import __version__

# Import refactored modules
from q_cli.config.manager import ConfigManager
from q_cli.cli.args import setup_argparse
from q_cli.cli.updates import handle_update_command, check_updates_async
from q_cli.cli.context_setup import (
    setup_context_and_prompts, 
    handle_context_confirmation,
    configure_file_tree
)
from q_cli.cli.session_handlers import (
    handle_recover_command,
    initialize_session_manager,
    setup_permission_manager
)
from q_cli.cli.llm_setup import (
    setup_api_credentials,
    initialize_llm_client
)
from q_cli.cli.dry_run import handle_dry_run
from q_cli.io.input import (
    create_prompt_session,
    get_initial_question
)
from q_cli.io.output import setup_console
from q_cli.cli.conversation import run_conversation
from q_cli.utils.constants import get_debug
from q_cli.config.providers import (
    get_default_model,
    get_max_tokens
)


def initialize_cli() -> Tuple[Any, Console]:
    """Initialize CLI arguments and console setup.
    
    Returns:
        Tuple containing parsed arguments and console
    """
    parser = setup_argparse()

    # If no args provided (sys.argv has just the script name), go into interactive mode
    if len(sys.argv) == 1:
        # Set the interactive mode flag to ensure we proceed with interactive mode
        sys.argv.append("--interactive")

    args = parser.parse_args()
    
    # Set debug mode if requested
    if args.debug:
        os.environ["Q_DEBUG"] = "true"
        # Just print a basic message for now - detailed logs will come from individual components
        print("Debug mode enabled")

    # Initialize console for output
    console = setup_console()
    
    return args, console


def configure_model_settings(args: Any, provider: str, config_vars: Dict[str, Any]) -> None:
    """Configure model and token settings based on provider.
    
    Args:
        args: Command line arguments
        provider: Provider name
        config_vars: Configuration variables
    """
    # Set model based on provider-specific configuration if not explicitly specified
    if not args.model:
        provider_lower = provider.lower()
        provider_upper = provider.upper()
        
        # Use provider-specific model setting
        model_config_key = f"{provider_upper}_MODEL"
        if model_config_key in config_vars:
            args.model = config_vars[model_config_key]
        else:
            args.model = get_default_model(provider_lower)
    
    # Set max_tokens based on provider-specific config
    provider_lower = provider.lower()
    max_tokens_key = f"{provider.upper()}_MAX_TOKENS"
    
    # Handle max_tokens which might be unset
    if not hasattr(args, "max_tokens") or args.max_tokens is None:
        if max_tokens_key in config_vars:
            try:
                max_tokens_value = config_vars.get(max_tokens_key)
                if isinstance(max_tokens_value, str):
                    # Clean up any comments in the value
                    if "#" in max_tokens_value:
                        max_tokens_value = max_tokens_value.split("#")[0].strip()
                args.max_tokens = int(max_tokens_value)
            except (ValueError, TypeError):
                # If conversion fails, use provider default
                args.max_tokens = get_max_tokens(provider_lower)
        else:
            # Default to a reasonable value if not specified
            args.max_tokens = get_max_tokens(provider_lower)


def execute_conversation(
    client, 
    system_prompt: str, 
    args: Any, 
    prompt_session, 
    console: Console, 
    question: str, 
    permission_manager, 
    context_manager, 
    auto_approve: bool, 
    session_manager
) -> None:
    """Run the conversation with error handling.
    
    Args:
        client: LLM client
        system_prompt: System prompt
        args: Command line arguments
        prompt_session: Prompt session for input
        console: Console for output
        question: Initial question
        permission_manager: Permission manager
        context_manager: Context manager
        auto_approve: Auto-approve flag
        session_manager: Session manager
    """
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
        if get_debug():
            import traceback
            console.print(f"[red]{traceback.format_exc()}[/red]")
        console.print(
            "[yellow]The application encountered an error and must exit.[/yellow]"
        )
        sys.exit(1)


def main() -> None:
    """Main entry point for the CLI."""
    try:
        # Initialize CLI arguments and console
        args, console = initialize_cli()
        
        # Handle update command if specified
        if handle_update_command(args):
            return  # Update was handled, exit
        
        # Handle recover command if specified
        if handle_recover_command(args, console):
            return  # Recovery was handled, exit
        
        # Async check for updates - don't block startup
        check_updates_async(console)
        
        # Initialize config manager and load config
        config_manager = ConfigManager(console)
        config_api_key, config_context, config_vars = config_manager.load_config()
        
        # Get provider and API key
        provider, api_key = setup_api_credentials(args, config_vars, console, config_api_key)
        
        # Configure model and token settings
        configure_model_settings(args, provider, config_vars)
        
        # Check for API key
        if not api_key:
            console.print(
                f"[bold red]Error: API key for {provider} not provided. Add to ~/.config/q.conf, set {provider.upper()}_API_KEY environment variable, or use --api-key[/bold red]"
            )
            sys.exit(1)
        
        # Initialize LLM client
        client = initialize_llm_client(api_key, args, provider, console)
        
        # Set up prompt session and history
        prompt_session = create_prompt_session(console)
        history = prompt_session.history
        
        # Display version and model info with absolute minimal visibility
        if not get_debug():  # Only print ultra-dim in regular mode
            version_str = f"Q ver. {__version__} - Brain: {args.model}"
            # Lightest possible gray that's still barely visible
            console.print(f"[dim #aaaaaa]{version_str}[/dim #aaaaaa]")
        
        # Configure file tree inclusion
        configure_file_tree(args, config_vars, console)
        
        # Set up context and system prompts
        context_manager, sanitized_context, system_prompt = setup_context_and_prompts(
            args, config_context, console, config_vars
        )
        
        # Handle context confirmation if needed
        if not handle_context_confirmation(args, prompt_session, sanitized_context, system_prompt, console):
            sys.exit(0)
        
        # Set up permissions
        permission_manager, auto_approve = setup_permission_manager(config_vars, args, console)
        
        # Get initial question
        try:
            question = get_initial_question(args, prompt_session, history)
        except (KeyboardInterrupt, EOFError):
            sys.exit(0)
        
        # Handle dry run mode if enabled
        if handle_dry_run(args, question, system_prompt, console):
            sys.exit(0)
        
        # Initialize session manager
        session_manager = initialize_session_manager(args, console)
        
        # Run the conversation
        execute_conversation(
            client,
            system_prompt,
            args,
            prompt_session,
            console,
            question,
            permission_manager,
            context_manager,
            auto_approve,
            session_manager
        )
        
    except Exception as e:
        # Last chance to catch any uncaught exceptions
        console = Console()
        console.print(f"\n[bold red]Fatal error: {str(e)}[/bold red]")
        if get_debug():
            import traceback
            console.print(f"[red]{traceback.format_exc()}[/red]")
        console.print(
            "[yellow]The application encountered a fatal error and must exit.[/yellow]"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()