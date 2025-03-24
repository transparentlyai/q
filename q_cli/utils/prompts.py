"""Prompt management for q_cli."""

import os
from typing import Optional

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


def get_system_prompt(
    include_command_execution: bool = False, context: Optional[str] = None
) -> str:
    """
    Build the complete system prompt from components.

    Args:
        include_command_execution: Whether to include command execution instructions (deprecated)
        context: Optional context to include

    Returns:
        Complete system prompt string
    """
    system_prompt = load_prompt("base_system_prompt")

    if context:
        context_template = load_prompt("context_prompt")
        system_prompt += f"\n\n{context_template.format(context=context)}"

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
        template = load_prompt("command_result_prompt")
        return template.format(results=results)
    except FileNotFoundError:
        # Fall back to a default format if the prompt file is missing
        return f"I ran the command(s) you suggested. Here are the results:\n\n{results}"
