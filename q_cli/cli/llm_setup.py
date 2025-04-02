"""LLM client setup for q_cli."""

import sys
import os
from typing import Any, Dict, Optional, Tuple
from rich.console import Console

from q_cli.config.providers import (
    is_valid_model_for_provider,
    format_model_name,
    SUPPORTED_PROVIDERS,
    DEFAULT_PROVIDER
)
from q_cli.utils.constants import get_debug


def validate_model_for_provider(model: str, provider: str, console: Console) -> bool:
    """Validate that the model is compatible with the provider.

    Args:
        model: Model name
        provider: Provider name
        console: Console instance for output

    Returns:
        True if valid, False otherwise
    """
    valid = is_valid_model_for_provider(model, provider)

    if not valid:
        console.print(
            f"[bold yellow]Warning: Model '{model}' doesn't appear to be a "
            f"{provider} model. This may cause errors.[/bold yellow]"
        )

    return valid


def initialize_llm_client(api_key: str, args: Any, provider: str, console: Console):
    """Initialize LLM client with error handling.

    Args:
        api_key: API key for the provider
        args: Command line arguments with model and provider_kwargs
        provider: Provider name
        console: Console for output

    Returns:
        Initialized LLM client
    """
    try:
        # Validate model compatibility with provider
        validate_model_for_provider(args.model, provider, console)

        # Lazy import LLMClient only when needed
        from q_cli.utils.client import LLMClient

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
            f"[bold red]Error initializing LLM client with provider {provider}: "
            f"{str(e)}[/bold red]"
        )
        console.print("[yellow]Please check your API key and try again.[/yellow]")
        raise


def setup_api_credentials(
    args: Any,
    config_vars: Dict[str, Any],
    console: Console,
    config_api_key: Optional[str]
) -> Tuple[str, Optional[str]]:
    """Set up API credentials and provider-specific configuration.

    Args:
        args: Command line arguments
        config_vars: Configuration variables
        console: Console for output
        config_api_key: API key from config file

    Returns:
        Tuple containing:
        - Provider name
        - API key (may be None)
    """
    # Validate the configuration
    from q_cli.io.config import validate_config
    try:
        validate_config(config_vars, console)
    except ValueError as e:
        if not args.provider:  # Only fail if user didn't override provider via args
            console.print(f"[bold red]Error: {str(e)}[/bold red]")
            sys.exit(1)
        else:
            # User specified provider via args, so just warn about config issues
            console.print(
                f"[bold yellow]Warning: Config validation failed but continuing "
                f"with provided args: {str(e)}[/bold yellow]"
            )

    # Get provider from args, config file, or default
    provider = args.provider or config_vars.get("PROVIDER", DEFAULT_PROVIDER)

    # Validate that provider is supported
    if provider.lower() not in map(str.lower, SUPPORTED_PROVIDERS):
        allowed = ", ".join(sorted(SUPPORTED_PROVIDERS))
        console.print(
            f"[bold red]Error: Provider '{provider}' is not supported. "
            f"Allowed providers: {allowed}[/bold red]"
        )
        sys.exit(1)

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
        # Clean up any comments in the value if it's a string
        if isinstance(api_key, str) and "#" in api_key:
            api_key = api_key.split("#")[0].strip()

        # Handle VertexAI project ID from config or environment
        project_id = (
            config_vars.get("VERTEXAI_PROJECT") or
            config_vars.get("VERTEX_PROJECT") or
            os.environ.get("VERTEXAI_PROJECT") or
            os.environ.get("VERTEX_PROJECT")
        )
        # Clean up any comments in the project ID value
        if isinstance(project_id, str) and "#" in project_id:
            project_id = project_id.split("#")[0].strip()
        if project_id:
            provider_kwargs["project_id"] = project_id
            if get_debug():
                console.print(f"[info]Using VertexAI project ID: {project_id}[/info]")
        else:
            console.print(
                "[bold red]ERROR: No project ID specified for VertexAI. "
                "Set VERTEXAI_PROJECT in config or environment.[/bold red]"
            )
            sys.exit(1)

        # Handle VertexAI location from config or environment
        location = (
            config_vars.get("VERTEXAI_LOCATION") or
            config_vars.get("VERTEX_LOCATION") or
            os.environ.get("VERTEXAI_LOCATION") or
            os.environ.get("VERTEX_LOCATION")
        )
        # Clean up any comments in the location value
        if isinstance(location, str) and "#" in location:
            location = location.split("#")[0].strip()
        if location:
            provider_kwargs["location"] = location
            if get_debug():
                console.print(f"[info]Using VertexAI location: {location}[/info]")
        else:
            console.print(
                "[bold red]ERROR: No location specified for VertexAI. "
                "Set VERTEXAI_LOCATION in config or environment.[/bold red]"
            )
            sys.exit(1)
    elif provider.lower() == "groq":
        api_key = config_vars.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY")
        # Clean up any comments in the value
        if isinstance(api_key, str) and "#" in api_key:
            api_key = api_key.split("#")[0].strip()
    elif provider.lower() == "openai":
        api_key = config_vars.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        # Clean up any comments in the value
        if isinstance(api_key, str) and "#" in api_key:
            api_key = api_key.split("#")[0].strip()
    else:
        # Fallback to generic API key or anthropic key for backward compatibility
        api_key = config_api_key or os.environ.get("API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        # Clean up any comments in the value
        if isinstance(api_key, str) and "#" in api_key:
            api_key = api_key.split("#")[0].strip()

    # Store provider_kwargs in args for later use when initializing client
    args.provider_kwargs = provider_kwargs

    return provider, api_key
