"""Context setup for q_cli.

This module handles the setup of context data for LLM queries.
"""

import os
import re
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
    
    # Get base system prompt (needed only for testing)
    # Not used directly, but needed to test variable subsitutiton

    # Get user context from q.conf
    user_context = ""
    from q_cli.utils.constants import CONFIG_PATH
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            content = f.read()
            # Find the CONTEXT section - look for both [CONTEXT] and #CONTEXT formats
            context_match = re.search(r'\[CONTEXT\](.*?)(\n\[|\Z)', content, re.DOTALL)
            if not context_match:
                # Try the alternate format with # instead of []
                # This captures everything after the #CONTEXT line until the end of file 
                # Using a more robust pattern that is specific to the structure of the config file
                # Skip comment lines to get to the actual content
                context_match = re.search(r'#CONTEXT.*?\n((?:- .*\n)+)', content, re.DOTALL)
            
            if context_match:
                user_context = context_match.group(1).strip()
    
    # Get project context from .Q/project.md and list available files in .Q directory
    project_context = ""
    q_dir_path = os.path.join(os.getcwd(), ".Q")
    project_md_path = os.path.join(q_dir_path, "project.md")
    
    # Read project.md content if exists
    if os.path.isdir(q_dir_path) and os.path.isfile(project_md_path):
        try:
            with open(project_md_path, "r") as f:
                project_context = f.read().strip()
        except Exception:
            pass
            
    # Add list of files in .Q directory if it exists
    if os.path.isdir(q_dir_path):
        try:
            q_files = os.listdir(q_dir_path)
            if q_files:
                # Filter out project.md as it's already included in content
                other_files = [f for f in q_files if f != "project.md"]
                if other_files:
                    file_list = "\n".join([f"- {file}" for file in other_files])
                    # Add file list to project_context
                    if project_context:
                        project_context += "\n\n"
                    project_context += f"Additional project information can be found in the following files:\n{file_list}"
        except Exception:
            pass
    
    # Use variables instead of appending context
    system_prompt = get_system_prompt(
        include_command_execution=include_command_execution,
        model=model_name,
        usercontext=user_context,
        projectcontext=project_context
    )

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
    # If confirm-context is specified, show the full context information and ask for confirmation
    if args.confirm_context:
        # Show both the sanitized context and the system prompt
        if sanitized_context:
            console.print("\n[bold cyan]Sanitized Context:[/bold cyan]")
            console.print(sanitized_context)
            console.print("")
        
        # Always show the system prompt, even if no sanitized context
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
