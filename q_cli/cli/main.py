"""Main entry point for the q_cli package."""

import os
import sys
from typing import Tuple, Dict, Any, Optional, List
from q_cli import __version__
from argparse import Namespace
from rich.console import Console


def get_debug():
    """Get the DEBUG value from environment, respecting any recent changes."""
    debug_val = os.environ.get("Q_DEBUG", "false").lower()
    return debug_val in ["true", "1", "yes", "y", "on"]


from q_cli.cli.args import setup_argparse
from q_cli.io.config import read_config_file, build_context
from q_cli.io.input import create_prompt_session, get_initial_question, confirm_context
from q_cli.io.output import setup_console
from q_cli.utils.constants import (
    DEFAULT_MODEL,
    DEFAULT_ALWAYS_APPROVED_COMMANDS,
    DEFAULT_ALWAYS_RESTRICTED_COMMANDS,
    DEFAULT_PROHIBITED_COMMANDS,
    ANTHROPIC_DEFAULT_MODEL,
    VERTEXAI_DEFAULT_MODEL,
    GROQ_DEFAULT_MODEL,
    OPENAI_DEFAULT_MODEL,
    ANTHROPIC_MAX_TOKENS,
    VERTEXAI_MAX_TOKENS,
    GROQ_MAX_TOKENS,
    OPENAI_MAX_TOKENS,
    DEFAULT_PROVIDER,
    SUPPORTED_PROVIDERS,
)
from q_cli.utils.helpers import sanitize_context
from q_cli.cli.conversation import run_conversation
from q_cli.utils.permissions import CommandPermissionManager
from q_cli.utils.prompts import get_system_prompt


def initialize_cli() -> Tuple[Namespace, Console]:
    """Initialize CLI arguments and console setup."""
    parser = setup_argparse()

    # If no args provided (sys.argv has just the script name), go into interactive mode
    if len(sys.argv) == 1:
        # Set the interactive mode flag to ensure we proceed with interactive mode
        sys.argv.append("--interactive")

    args = parser.parse_args()
    
    # Set debug mode if requested
    if args.debug:
        os.environ["Q_DEBUG"] = "true"
        # We need to reload the DEBUG constant after changing the environment variable
        print(f"Debug mode enabled")

    # Initialize console for output
    console = setup_console()
    
    return args, console


def handle_update_command(args: Namespace) -> None:
    """Handle the update command if specified."""
    if args.update:
        from q_cli.cli.args import update_command
        update_command()
        sys.exit(0)


def get_config_for_recovery(args: Namespace, console: Console) -> Tuple[str, Dict[str, Any], str]:
    """Get configuration for session recovery."""
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
        # Handle VertexAI project ID from config or environment
        if project_id := config_vars.get("VERTEXAI_PROJECT"):
            os.environ["VERTEXAI_PROJECT"] = project_id
        elif project_id := config_vars.get("VERTEX_PROJECT"):
            os.environ["VERTEX_PROJECT"] = project_id
            
        # Handle VertexAI location from config or environment
        if location := config_vars.get("VERTEXAI_LOCATION"):
            os.environ["VERTEXAI_LOCATION"] = location
        elif location := config_vars.get("VERTEX_LOCATION"):
            os.environ["VERTEX_LOCATION"] = location
    elif provider.lower() == "groq":
        api_key = config_vars.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY")
    elif provider.lower() == "openai":
        api_key = config_vars.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
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
        elif provider.lower() == "openai":
            args.model = config_vars.get("MODEL", OPENAI_DEFAULT_MODEL)
        else:
            args.model = config_vars.get("MODEL", DEFAULT_MODEL)
            
    # Set max_tokens based on provider-specific config or default
    if provider.lower() == "anthropic":
        args.max_tokens = int(config_vars.get("ANTHROPIC_MAX_TOKENS", ANTHROPIC_MAX_TOKENS))
    elif provider.lower() == "vertexai":
        args.max_tokens = int(config_vars.get("VERTEXAI_MAX_TOKENS", VERTEXAI_MAX_TOKENS))
    elif provider.lower() == "groq":
        args.max_tokens = int(config_vars.get("GROQ_MAX_TOKENS", GROQ_MAX_TOKENS))
    elif provider.lower() == "openai":
        args.max_tokens = int(config_vars.get("OPENAI_MAX_TOKENS", OPENAI_MAX_TOKENS))
    else:
        args.max_tokens = int(config_vars.get(f"{provider.upper()}_MAX_TOKENS", ANTHROPIC_MAX_TOKENS))

    # Force interactive mode when recovering
    args.no_interactive = False
    args.interactive = True
    
    return api_key, config_vars, provider


def handle_recover_command(args: Namespace, console: Console) -> None:
    """Handle the recover command if specified."""
    if not args.recover:
        return
        
    from q_cli.utils.session.manager import recover_session
    from q_cli.utils.client import LLMClient

    try:
        # Get configuration for recovery
        api_key, config_vars, provider = get_config_for_recovery(args, console)
        
        # Check for API key
        if not api_key:
            console.print(
                f"[bold red]Error: API key for {provider} not provided. Add to ~/.config/q.conf, set {provider.upper()}_API_KEY environment variable, or use --api-key[/bold red]"
            )
            sys.exit(1)
            
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
        if get_debug():
            import traceback
            console.print(f"[red]{traceback.format_exc()}[/red]")
        # Continue with normal startup


def check_updates_async(console: Console) -> None:
    """Check for updates asynchronously without blocking startup."""
    from threading import Thread
    from q_cli.utils.helpers import check_for_updates, is_newer_version

    def _check_update():
        update_available, latest_version = check_for_updates(console)
        if update_available:
            msg = f"[dim]New version {latest_version} available. Run 'q --update' to update.[/dim]"
            console.print(msg)
        
        # Debug version check information
        if get_debug():
            console.print(
                f"[dim]Current version: {__version__}, Latest version from GitHub: {latest_version or 'not found'}[/dim]"
            )
            if latest_version:
                is_newer = is_newer_version(latest_version, __version__)
                console.print(f"[dim]Is GitHub version newer: {is_newer}[/dim]")
    
    # Run in background thread to avoid blocking startup
    update_thread = Thread(target=_check_update)
    update_thread.daemon = True
    update_thread.start()


def setup_api_credentials(args: Namespace, config_vars: Dict[str, Any], console: Console, config_api_key: str) -> Tuple[str, str]:
    """Set up API credentials and provider-specific configuration."""
    # Get provider from args, config file, or default
    provider = args.provider or config_vars.get("PROVIDER", DEFAULT_PROVIDER)
    
    # Initialize provider_kwargs for any provider-specific settings
    provider_kwargs = {}
    
    # Get API key based on provider
    if args.api_key:
        # Use API key from args
        api_key = args.api_key
    elif provider.lower() == "anthropic":
        api_key = config_vars.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    elif provider.lower() == "vertexai":
        api_key = config_vars.get("VERTEXAI_API_KEY") or os.environ.get("VERTEXAI_API_KEY")
        
        # Handle VertexAI project ID from config or environment
        project_id = config_vars.get("VERTEXAI_PROJECT") or config_vars.get("VERTEX_PROJECT") or os.environ.get("VERTEXAI_PROJECT") or os.environ.get("VERTEX_PROJECT")
        if project_id:
            provider_kwargs["project_id"] = project_id
            if get_debug():
                console.print(f"[info]Using VertexAI project ID: {project_id}[/info]")
        else:
            console.print("[bold yellow]WARNING: No project ID specified for VertexAI. Set VERTEXAI_PROJECT in config or environment.[/bold yellow]")
            
        # Handle VertexAI location from config or environment
        location = config_vars.get("VERTEXAI_LOCATION") or config_vars.get("VERTEX_LOCATION") or os.environ.get("VERTEXAI_LOCATION") or os.environ.get("VERTEX_LOCATION")
        if location:
            provider_kwargs["location"] = location
            if get_debug():
                console.print(f"[info]Using VertexAI location: {location}[/info]")
        else:
            console.print("[bold yellow]WARNING: No location specified for VertexAI. Set VERTEXAI_LOCATION in config or environment.[/bold yellow]")
    elif provider.lower() == "groq":
        api_key = config_vars.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY")
    elif provider.lower() == "openai":
        api_key = config_vars.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    else:
        # Fallback to generic API key or anthropic key for backward compatibility
        api_key = config_api_key or os.environ.get("API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    
    # Store provider_kwargs in args for later use when initializing client
    args.provider_kwargs = provider_kwargs
        
    return provider, api_key


def configure_model_settings(args: Namespace, provider: str, config_vars: Dict[str, Any]) -> None:
    """Configure model and token settings based on provider."""
    # Set model based on provider if not explicitly specified
    if not args.model:
        if provider.lower() == "anthropic":
            args.model = config_vars.get("MODEL", ANTHROPIC_DEFAULT_MODEL)
        elif provider.lower() == "vertexai":
            args.model = config_vars.get("MODEL", VERTEXAI_DEFAULT_MODEL)
        elif provider.lower() == "groq":
            args.model = config_vars.get("MODEL", GROQ_DEFAULT_MODEL)
        elif provider.lower() == "openai":
            args.model = config_vars.get("MODEL", OPENAI_DEFAULT_MODEL)
        else:
            args.model = config_vars.get("MODEL", DEFAULT_MODEL)
    
    # Set max_tokens based on provider-specific config or default
    if provider.lower() == "anthropic":
        args.max_tokens = int(config_vars.get("ANTHROPIC_MAX_TOKENS", ANTHROPIC_MAX_TOKENS))
    elif provider.lower() == "vertexai":
        args.max_tokens = int(config_vars.get("VERTEXAI_MAX_TOKENS", VERTEXAI_MAX_TOKENS))
    elif provider.lower() == "groq":
        args.max_tokens = int(config_vars.get("GROQ_MAX_TOKENS", GROQ_MAX_TOKENS))
    elif provider.lower() == "openai":
        args.max_tokens = int(config_vars.get("OPENAI_MAX_TOKENS", OPENAI_MAX_TOKENS))
    else:
        args.max_tokens = int(config_vars.get(f"{provider.upper()}_MAX_TOKENS", ANTHROPIC_MAX_TOKENS))


def initialize_llm_client(api_key: str, args: Namespace, provider: str, console: Console):
    """Initialize LLM client with error handling."""
    try:
        # Lazy import LLMClient only when needed
        from q_cli.utils.client import LLMClient
        import litellm  # Only import when we're about to use it
        
        # Get provider-specific kwargs if available
        provider_kwargs = getattr(args, "provider_kwargs", {})
        
        # Initialize our LLM client wrapper
        client = LLMClient(
            api_key=api_key, 
            model=args.model, 
            provider=provider,
            **provider_kwargs
        )
        
        if get_debug():
            console.print(f"[dim]Using provider: {provider}, model: {args.model}[/dim]")
            
        return client
    
    except Exception as e:
        console.print(
            f"[bold red]Error initializing LLM client with provider {provider}: {str(e)}[/bold red]"
        )
        console.print("[yellow]Please check your API key and try again.[/yellow]")
        sys.exit(1)


def configure_file_tree(args: Namespace, config_vars: Dict[str, Any], console: Console) -> None:
    """Configure file tree inclusion settings."""
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

        if get_debug():
            console.print("[info]File tree will be included in context[/info]")


def setup_context_and_prompts(args: Namespace, config_context: str, console: Console, config_vars: Dict[str, Any]):
    """Set up context and system prompts."""
    # Build and sanitize context from config and files
    context, context_manager = build_context(args, config_context, console, config_vars)
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
    
    return context_manager, sanitized_context, system_prompt


def handle_context_confirmation(args: Namespace, prompt_session, sanitized_context, system_prompt, console: Console) -> None:
    """Handle context confirmation if needed."""
    # If confirm-context is specified, show the context and ask for confirmation
    if args.confirm_context and sanitized_context:
        if not confirm_context(prompt_session, system_prompt, console):
            console.print("Context rejected. Exiting.", style="info")
            sys.exit(0)


def setup_permissions(config_vars: Dict[str, Any], args: Namespace):
    """Set up permission manager and auto-approve settings."""
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


def handle_dry_run(args: Namespace, question: str, system_prompt: str, console: Console) -> None:
    """Handle dry run mode if enabled."""
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


def initialize_session_manager(args: Namespace, console: Console):
    """Initialize session manager if needed."""
    session_manager = None
    if not getattr(args, "no_save", False):
        from q_cli.utils.session.manager import SessionManager
        session_manager = SessionManager(console)
    return session_manager


def execute_conversation(client, system_prompt, args, prompt_session, console, question, permission_manager, context_manager, auto_approve, session_manager):
    """Run the conversation with error handling."""
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
    # Initialize CLI arguments and console
    args, console = initialize_cli()
    
    # Handle update command if specified
    handle_update_command(args)
    
    # Handle recover command if specified
    handle_recover_command(args, console)
    
    # Async check for updates - don't block startup
    check_updates_async(console)
    
    # Get API key and config vars from config file
    config_api_key, config_context, config_vars = read_config_file(console)
    
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
    
    # Configure file tree inclusion
    configure_file_tree(args, config_vars, console)
    
    # Set up context and system prompts
    context_manager, sanitized_context, system_prompt = setup_context_and_prompts(
        args, config_context, console, config_vars
    )
    
    # Handle context confirmation if needed
    handle_context_confirmation(args, prompt_session, sanitized_context, system_prompt, console)
    
    # Set up permissions
    permission_manager, auto_approve = setup_permissions(config_vars, args)
    
    # Get initial question
    try:
        question = get_initial_question(args, prompt_session, history)
    except (KeyboardInterrupt, EOFError):
        sys.exit(0)
    
    # Handle dry run mode if enabled
    handle_dry_run(args, question, system_prompt, console)
    
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


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Last chance to catch any uncaught exceptions
        # Import console here since we might not have it initialized
        from rich.console import Console

        console = Console()
        console.print(f"\n[bold red]Fatal error: {str(e)}[/bold red]")
        if get_debug():
            import traceback
            console.print(f"[red]{traceback.format_exc()}[/red]")
        console.print(
            "[yellow]The application encountered a fatal error and must exit.[/yellow]"
        )
        sys.exit(1)
