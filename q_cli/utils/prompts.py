"""Prompt management for q_cli."""

import os
from typing import Any, Optional

from q_cli.utils.constants import PROMPTS_DIR


def load_prompt(prompt_name: str) -> str:
    """
    Load a prompt from a file in the prompts directory.

    Args:
        prompt_name: Name of the prompt file (without .md extension)

    Returns:
        The content of the prompt file

    Raises:
        FileNotFoundError: If the prompt file doesn't exist
    """
    prompt_path = os.path.join(PROMPTS_DIR, f"{prompt_name}.md")

    with open(prompt_path, "r") as f:
        return f.read().strip()


def get_prompt(file_path: str, **kwargs: Any) -> str:
    """
    Load a prompt from a file and substitute variables.
    Note: This function deliberately does not cache results to ensure fresh prompt content.

    Args:
        file_path: Path to the prompt file
        **kwargs: Variables to substitute in the prompt

    Returns:
        The prompt with variables substituted

    Raises:
        FileNotFoundError: If the prompt file doesn't exist
    """
    # Read the file contents directly every time
    with open(file_path, "r") as f:
        prompt = f.read().strip()
    
    # Perform the substitution
    result = prompt.format(**kwargs)
    
    # If model is provided, always ensure it's correctly substituted
    if 'model' in kwargs:
        # Ensure the model name is in the prompt via direct replacement
        import re
        pattern = r'Your are currently using .+ as your primary model'
        replacement = f'Your are currently using {kwargs["model"]} as your primary model'
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    return result


def get_system_prompt(
    include_command_execution: bool = False, 
    context: Optional[str] = None, 
    model: Optional[str] = None
) -> str:
    """
    Build the complete system prompt from components.

    Args:
        include_command_execution: Whether to include command execution instructions (deprecated)
        context: Optional context to include
        model: Optional model name (unused, kept for backwards compatibility)

    Returns:
        Complete system prompt string
    """
    prompt_path = os.path.join(PROMPTS_DIR, "base_system_prompt.md")
    system_prompt = get_prompt(prompt_path, model=model or "")
    
    if context:
        context_path = os.path.join(PROMPTS_DIR, "context_prompt.md")
        context_prompt = get_prompt(context_path, context=context)
        system_prompt += f"\n\n{context_prompt}"

    return system_prompt


def get_command_result_prompt(results: str) -> str:
    """
    Get the prompt for command result analysis.

    Args:
        results: Command execution results

    Returns:
        Formatted prompt for command result analysis
    """
    try:
        prompt_path = os.path.join(PROMPTS_DIR, "command_result_prompt.md")
        return get_prompt(prompt_path, results=results)
    except FileNotFoundError:
        # Fall back to a default format if the prompt file is missing
        return f"I ran the command(s) you suggested. Here are the results:\n\n{results}"
