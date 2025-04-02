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

    # If usercontext or projectcontext are provided but empty,
    # keep them empty to preserve the prompt structure exactly as intended
    # Ensure the variables are always present in kwargs to prevent KeyError
    if "usercontext" not in kwargs:
        kwargs["usercontext"] = ""
    if "projectcontext" not in kwargs:
        kwargs["projectcontext"] = ""

    # Debug message for variable substitution issues
    from q_cli.utils.constants import get_debug, CONFIG_PATH

    if get_debug():
        print(f"Variables being substituted: {sorted(kwargs.keys())}")
        print(f"usercontext: '{kwargs.get('usercontext', 'NOT PROVIDED')}'")
        print(f"projectcontext: '{kwargs.get('projectcontext', 'NOT PROVIDED')}'")

        # DEBUG: Show the actual content of q.conf to help diagnose regex issues
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    config_content = f.read()
                    # Only display relevant portion containing CONTEXT
                    context_section = ""
                    lines = config_content.split("\n")
                    for i, line in enumerate(lines):
                        if "#CONTEXT" in line and i + 1 < len(lines):
                            # Get up to 10 lines after CONTEXT
                            context_section = "\n".join(
                                lines[i : min(i + 10, len(lines))]
                            )
                            break
                    if context_section:
                        print(
                            f"Q.conf #CONTEXT section (first 10 lines):\n{context_section}"
                        )
            except Exception as e:
                print(f"Error reading q.conf: {e}")

    try:
        # Perform the substitution
        result = prompt.format(**kwargs)
    except KeyError as e:
        # Handle missing format variables
        if get_debug():
            print(f"Error in format substitution: Missing key {e}")

        # Add missing keys with placeholder values to prevent errors
        missing_key = str(e).strip("'")
        kwargs[missing_key] = f"[Missing value for {missing_key}]"
        result = prompt.format(**kwargs)

    # If model is provided, always ensure it's correctly substituted
    if "model" in kwargs:
        # Ensure the model name is in the prompt via direct replacement
        import re

        pattern = r"Your are currently using .+ as your primary model"
        replacement = (
            f'Your are currently using {kwargs["model"]} as your primary model'
        )
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    # The Important Contextual Variables section has been intentionally removed from the prompt
    # No additional changes needed here for that section

    # Final check: Make sure the variables are appearing correctly in the prompt
    # Debug message to report what ended up in the result
    if get_debug() and result:
        lines = result.split("\n")
        user_context_content = ""
        project_context_content = ""

        for i, line in enumerate(lines):
            if "User context:" in line and i + 1 < len(lines):
                user_context_content = lines[i + 1].strip()
            if "Project context:" in line and i + 1 < len(lines):
                project_context_content = lines[i + 1].strip()

        if "usercontext" in kwargs or "projectcontext" in kwargs:
            print(f"Final user context in prompt: {user_context_content or '(empty)'}")
            print(
                f"Final project context in prompt: {project_context_content or '(empty)'}"
            )

    return result


def get_system_prompt(
    include_command_execution: bool = False,
    context: Optional[str] = None,
    model: Optional[str] = None,
    usercontext: str = "",
    projectcontext: str = "",
) -> str:
    """
    Build the complete system prompt from components.

    Args:
        include_command_execution: Whether to include command execution instructions (deprecated)
        context: Optional context to include (deprecated, use usercontext and projectcontext instead)
        model: Optional model name
        usercontext: User context from q.conf
        projectcontext: Project context from .Q/project.md

    Returns:
        Complete system prompt string
    """
    prompt_path = os.path.join(PROMPTS_DIR, "base_system_prompt.md")
    system_prompt = get_prompt(
        prompt_path,
        model=model or "",
        usercontext=usercontext,
        projectcontext=projectcontext,
    )

    # For backwards compatibility, if context is provided but no usercontext/projectcontext
    if context and not (usercontext or projectcontext):
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
