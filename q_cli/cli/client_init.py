"""Client initialization for q_cli.

This module handles the initialization of LLM clients based on configuration.
"""

from typing import Any
from rich.console import Console

from q_cli.utils.constants import get_debug
from q_cli.config.providers import (
    is_valid_model_for_provider,
    format_model_name
)


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
        args: Command line arguments
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

        # Format model name according to provider conventions
        model = format_model_name(provider, args.model)

        # Initialize our LLM client wrapper
        client = LLMClient(
            api_key=api_key,
            model=model,
            provider=provider,
            **provider_kwargs
        )

        if get_debug():
            console.print(f"[dim]Using provider: {provider}, model: {model}[/dim]")

        return client

    except Exception as e:
        console.print(
            f"[bold red]Error initializing LLM client with provider {provider}: "
            f"{str(e)}[/bold red]"
        )
        console.print("[yellow]Please check your API key and try again.[/yellow]")
        raise