"""Configuration file handling for q_cli."""

import os
from typing import Dict, Optional, Tuple

from rich.console import Console

from q_cli.utils.constants import CONFIG_PATH, REDACTED_TEXT
from q_cli.utils.helpers import contains_sensitive_info, expand_env_vars


def read_config_file(console: Console) -> Tuple[Optional[str], str, Dict[str, str]]:
    """
    Read the configuration file for API key and context.

    Returns:
        Tuple containing:
        - API key (or None if not found)
        - Context string
        - Dictionary of configuration variables
    """
    api_key = None
    config_vars = {}
    context = ""
    context_started = False

    # Get repository root path
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # Create example config path for reference
    example_config_path = os.path.join(repo_root, "example_config.conf")

    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                for line in f:
                    line = line.strip()

                    # Check for context section marker
                    if line == "#CONTEXT":
                        context_started = True
                        continue

                    # Skip comments (but not in context section)
                    if line.startswith("#") and not context_started:
                        continue

                    if context_started:
                        # Filter out potential API keys in context
                        if contains_sensitive_info(line):
                            line = REDACTED_TEXT
                        context += line + "\n"
                    else:
                        # Parse configuration variables (KEY=value format)
                        if "=" in line:
                            key, value = line.split("=", 1)
                            key = key.strip().upper()
                            value = value.strip()

                            # Expand environment variables in value
                            if "$" in value:
                                value = expand_env_vars(value)

                            # Store in config vars
                            config_vars[key] = value

                            # Check for API key specifically
                            if key == "ANTHROPIC_API_KEY" and not api_key:
                                api_key = value
                        # Check for API key (assuming it's just the key on a line by itself)
                        elif (
                            not api_key and len(line) > 20
                        ):  # Simple validation for API key-like string
                            if line.startswith(
                                "sk-ant-api"
                            ):  # Strict validation for v1 API key format
                                api_key = line
        except Exception as e:
            console.print(f"Warning: Error reading config file: {e}", style="warning")
    else:
        # If config file doesn't exist, create a base one with default settings
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

            # If example config exists, use it as template, otherwise create minimal config
            if os.path.exists(example_config_path):
                with open(example_config_path, "r") as src, open(
                    CONFIG_PATH, "w"
                ) as dest:
                    dest.write(src.read())
                console.print(
                    f"[green]Created config file at {CONFIG_PATH} using example template.[/green]"
                )
            else:
                # Use the already defined example_config_path
                
                with open(example_config_path, "r") as src, open(CONFIG_PATH, "w") as dest:
                    dest.write(src.read())
                
                console.print(
                    f"[green]Created default config file at {CONFIG_PATH}.[/green]"
                )

            console.print(
                "Make sure your API key is set either in the config file or as ANTHROPIC_API_KEY environment variable.",
                style="info",
            )
        except Exception as e:
            console.print(f"[red]Error creating config file: {e}[/red]")
            console.print(
                f"You can manually create one at {CONFIG_PATH}",
                style="info",
            )

    return api_key, context.strip(), config_vars


def read_context_file(file_path: str, console: Console) -> str:
    """
    Read a context file and return its contents, ensuring no API keys are included.

    Args:
        file_path: Path to the context file to read
        console: Console instance for output

    Returns:
        The sanitized content of the file as a string
    """
    try:
        with open(file_path, "r") as f:
            content = f.read()
            # Filter out potential API keys (simple pattern matching)
            filtered_lines = []
            for line in content.split("\n"):
                # Skip lines that look like API keys
                if contains_sensitive_info(line):
                    filtered_lines.append(REDACTED_TEXT)
                else:
                    filtered_lines.append(line)
            return "\n".join(filtered_lines)
    except Exception as e:
        console.print(
            f"Warning: Error reading context file {file_path}: {e}", style="warning"
        )
        return ""


def build_context(args, config_context: str, console: Console) -> str:
    """
    Build the context from config and additional context files.

    Args:
        args: Command line arguments
        config_context: Context from the config file
        console: Console instance for output

    Returns:
        Combined context string
    """
    context = ""

    # Add config context if not disabled
    if config_context and not args.no_context:
        context += config_context + "\n\n"

    # Add context from additional files
    if args.context_file:
        for file_path in args.context_file:
            file_content = read_context_file(file_path, console)
            if file_content:
                context += (
                    f"Content from {os.path.basename(file_path)}:\n{file_content}\n\n"
                )

    context = context.strip()

    # Debug output
    if context and os.environ.get("Q_DEBUG"):
        console.print(f"[info]Context from config: {bool(config_context)}[/info]")
        console.print(f"[info]Context files: {args.context_file or []}[/info]")
        console.print(
            f"[info]Combined context length: {len(context)} characters[/info]"
        )

    return context
