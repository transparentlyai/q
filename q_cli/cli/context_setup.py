"""Context setup for q_cli.

This module handles the setup of context data for LLM queries.
"""

from typing import Any, Dict, Optional, Tuple
from rich.console import Console

from q_cli.utils.helpers import sanitize_context
from q_cli.io.config import build_context
from q_cli.utils.prompts import get_system_prompt
from q_cli.io.input import confirm_context


def setup_context_and_prompts(
    args: Any,
    config_context: Optional[str],
    console: Console,
    config_vars: Dict[str, Any]
) -> Tuple[Any, str, str]:
    """Set up context and system prompts.

    Args:
        args: Command line arguments
        config_context: Context from configuration
        console: Console for output
        config_vars: Configuration variables

    Returns:
        Tuple containing:
        - Context manager
        - Sanitized context
        - System prompt
    """
    # Build and sanitize context from config and files
    context, context_manager = build_context(args, config_context, console, config_vars)
    sanitized_context = sanitize_context(context, console)

    # Set up system prompt with context if available
    include_command_execution = not getattr(args, "no_execute", False)
    
    # Get the model name from args to substitute in the prompt
    model_name = getattr(args, "model", None)
    
    base_system_prompt = get_system_prompt(
        include_command_execution=include_command_execution,
        context=None,  # We'll set context separately
        model=model_name,
    )

    # Set system prompt and add conversation context
    if sanitized_context:
        # Context is now managed by the ContextManager
        system_prompt = get_system_prompt(
            include_command_execution=include_command_execution,
            context=sanitized_context,
            model=model_name,
        )
    else:
        system_prompt = base_system_prompt

    # Make sure the context manager knows about the system prompt
    context_manager.set_system_prompt(system_prompt)

    return context_manager, sanitized_context, system_prompt


def handle_context_confirmation(
    args: Any,
    prompt_session,
    sanitized_context: str,
    system_prompt: str,
    console: Console
) -> bool:
    """Handle context confirmation if needed.

    Args:
        args: Command line arguments
        prompt_session: Prompt session for input
        sanitized_context: Sanitized context
        system_prompt: System prompt
        console: Console for output

    Returns:
        True if context was confirmed or confirmation not needed, False to exit
    """
    # If confirm-context is specified, show the context and ask for confirmation
    if args.confirm_context and sanitized_context:
        if not confirm_context(prompt_session, system_prompt, console):
            console.print("Context rejected. Exiting.", style="info")
            return False

    return True


def configure_file_tree(args: Any, config_vars: Dict[str, Any], console: Console) -> None:
    """Configure file tree inclusion settings.

    Args:
        args: Command line arguments
        config_vars: Configuration variables
        console: Console for output
    """
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
        # Set the constant directly - need to modify module attribute
        import q_cli.utils.constants
        q_cli.utils.constants.INCLUDE_FILE_TREE = True

        from q_cli.utils.constants import get_debug
        if get_debug():
            console.print("[info]File tree will be included in context[/info]")
