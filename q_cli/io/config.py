"""Configuration file handling for q_cli."""

import os
import sys
import subprocess
from typing import Dict, Optional, Tuple, List

from rich.console import Console

from q_cli.utils.constants import (
    CONFIG_PATH,
    REDACTED_TEXT,
    get_debug,
    INCLUDE_FILE_TREE,
    MAX_FILE_TREE_ENTRIES,
    DEFAULT_MAX_CONTEXT_TOKENS,
    DEFAULT_CONTEXT_PRIORITY_MODE,
    ESSENTIAL_PRIORITY,
    IMPORTANT_PRIORITY,
    SUPPLEMENTARY_PRIORITY,
)
from q_cli.utils.helpers import contains_sensitive_info, expand_env_vars
from q_cli.utils.context import ContextManager
from q_cli.config.manager import ConfigManager


def validate_config(config_vars: Dict[str, str], console: Console) -> None:
    """
    Validate configuration variables for consistency and correctness.
    
    Args:
        config_vars: Dictionary of configuration variables
        console: Console instance for output
        
    Raises:
        ValueError: If configuration is invalid
    """
    # Use the ConfigManager's validation
    config_manager = ConfigManager(console)
    config_manager.config_vars = config_vars
    
    if not config_manager.validate_config():
        raise ValueError("Configuration validation failed")


def read_config_file(console: Console) -> Tuple[Optional[str], str, Dict[str, str]]:
    """
    Read the configuration file for API key and context.

    Returns:
        Tuple containing:
        - API key (or None if not found)
        - Context string
        - Dictionary of configuration variables
    """
    # Use the new ConfigManager
    config_manager = ConfigManager(console)
    return config_manager.load_config()


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


def update_config_provider(new_provider: str, console: Console, model: str = None) -> bool:
    """
    Update the configuration file with a new provider and optionally a new model.
    
    Args:
        new_provider: The new provider to set as default
        console: Console instance for output
        model: Optional model to set as the provider's default model
        
    Returns:
        True if the update was successful, False otherwise
    """
    # Use the ConfigManager
    config_manager = ConfigManager(console)
    return config_manager.update_config_provider(new_provider, model)


def build_context(
    args, config_context: str, console: Console, config_vars: Dict[str, str] = None
) -> Tuple[str, ContextManager]:
    """
    Build the context from config and additional context files using priority-based management.

    Args:
        args: Command line arguments
        config_context: Context from the config file
        console: Console instance for output
        config_vars: Configuration variables dictionary

    Returns:
        Tuple containing:
        - Combined context string
        - ContextManager instance
    """
    # Import provider-specific constants
    from q_cli.config.providers import (
        DEFAULT_PROVIDER,
        get_max_context_tokens
    )
    
    # Initialize with empty dict if not provided
    config_vars = config_vars or {}
    
    # Initialize context manager with args or provider-specific or default values
    provider = getattr(args, "provider", DEFAULT_PROVIDER)
    
    # Get provider-specific context token limit or global limit
    if not provider:
        provider = DEFAULT_PROVIDER
        
    # Set max_context_tokens based on provider
    if max_tokens := getattr(args, "max_context_tokens", None):
        # User explicitly specified value, use it
        pass
    else:
        # Get provider-specific token limit
        max_tokens = get_max_context_tokens(provider)
        
        # Check if there's a config override
        provider_key = f"{provider.upper()}_MAX_CONTEXT_TOKENS"
        if provider_key in config_vars:
            config_value = config_vars[provider_key]
            # Remove inline comments if present
            if "#" in config_value:
                config_value = config_value.split("#")[0].strip()
            max_tokens = int(config_value)
    
    priority_mode = getattr(
        args, "context_priority_mode", DEFAULT_CONTEXT_PRIORITY_MODE
    )

    context_manager = ContextManager(
        max_tokens=max_tokens, priority_mode=priority_mode, console=console
    )

    # Add config context if not disabled (supplementary priority)
    if config_context and not args.no_context:
        context_manager.add_context(
            config_context, SUPPLEMENTARY_PRIORITY, "Config file context"
        )

    # Add context from additional files (important priority)
    if args.context_file:
        for file_path in args.context_file:
            file_content = read_context_file(file_path, console)
            if file_content:
                context_manager.add_context(
                    f"Content from {os.path.basename(file_path)}:\n{file_content}",
                    IMPORTANT_PRIORITY,
                    f"File context: {os.path.basename(file_path)}",
                )

    # Add the current directory file tree to the context if enabled (important priority)
    if INCLUDE_FILE_TREE:
        file_tree = generate_file_tree(console)
        if file_tree:
            context_manager.add_context(
                "Current directory file structure:\n```\n" + file_tree + "\n```",
                IMPORTANT_PRIORITY,
                "File tree",
            )

            if get_debug():
                console.print("[info]Added file tree to context[/info]")

    # Check for .Q directory in current working directory
    q_dir_path = os.path.join(os.getcwd(), ".Q")
    if os.path.isdir(q_dir_path):
        # Get all files in .Q directory
        try:
            q_files = os.listdir(q_dir_path)
            if q_files:
                file_list = "\n".join([f"- {file}" for file in q_files])
                context_manager.add_context(
                    f"Project .Q directory contents:\n{file_list}",
                    IMPORTANT_PRIORITY,
                    ".Q directory files",
                )
                if get_debug():
                    console.print(
                        f"[info]Added {len(q_files)} files from .Q directory to context[/info]"
                    )
        except Exception as e:
            if get_debug():
                console.print(f"[yellow]Error reading .Q directory: {str(e)}[/yellow]")

    # Check for project.md file inside the .Q directory
    project_md_path = os.path.join(q_dir_path, "project.md")
    if os.path.isdir(q_dir_path) and os.path.isfile(project_md_path):
        try:
            project_content = read_context_file(project_md_path, console)
            if project_content:
                context_manager.add_context(
                    f"Project Information:\n{project_content}",
                    IMPORTANT_PRIORITY,
                    "project.md content",
                )
                if get_debug():
                    console.print("[info]Added .Q/project.md content to context[/info]")
        except Exception as e:
            if get_debug():
                console.print(f"[yellow]Error reading .Q/project.md: {str(e)}[/yellow]")

    # Build the final context string
    context = context_manager.build_context_string()

    # Show context stats if requested
    if getattr(args, "context_stats", False):
        tokens_by_priority = context_manager.get_tokens_by_priority()
        total_tokens = context_manager.get_total_tokens()

        console.print("\n[bold]Context Statistics:[/bold]")
        console.print(f"Total context tokens: {total_tokens}/{max_tokens}")
        console.print(f"System prompt: {tokens_by_priority['system']} tokens")
        console.print(
            f"Essential context: {tokens_by_priority[ESSENTIAL_PRIORITY]} tokens"
        )
        console.print(
            f"Important context: {tokens_by_priority[IMPORTANT_PRIORITY]} tokens"
        )
        console.print(
            f"Supplementary context: {tokens_by_priority[SUPPLEMENTARY_PRIORITY]} tokens"
        )
        console.print("")

    return context, context_manager


def generate_file_tree(console: Console) -> str:
    """
    Generate a tree view of the current directory.

    Returns:
        A string representation of the directory tree
    """
    try:
        # Check if 'tree' command is available
        try:
            # Try using the tree command first for better formatting
            # Exclude common directories to avoid clutter
            tree_cmd = [
                "tree",
                "-L",
                "3",
                "--noreport",
                "-I",
                "node_modules|venv|__pycache__|.git|.idea|.vscode|dist|build",
            ]

            result = subprocess.run(
                tree_cmd, capture_output=True, text=True, check=False
            )

            if result.returncode == 0 and result.stdout.strip():
                tree_output = result.stdout.strip()
                if get_debug():
                    console.print(
                        f"[info]Generated file tree using 'tree' command[/info]"
                    )
                return tree_output
        except FileNotFoundError:
            # Tree command not available, we'll use the fallback method
            if get_debug():
                console.print(
                    "[yellow]'tree' command not found, using fallback method[/yellow]"
                )
            pass

        # Fallback to find command
        cmd = [
            "find",
            ".",
            "-type",
            "d",
            "-o",
            "-type",
            "f",
            "-not",
            "-path",
            "*/\\.*",
            "-not",
            "-path",
            "*/venv/*",
            "-not",
            "-path",
            "*/node_modules/*",
            "-not",
            "-path",
            "*/__pycache__/*",
            "-not",
            "-path",
            "*/dist/*",
            "-not",
            "-path",
            "*/build/*",
            "-maxdepth",
            "3",
        ]

        # Execute the find command
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            if get_debug():
                console.print(
                    f"[yellow]Error generating file tree: {result.stderr}[/yellow]"
                )
            return ""

        # Process the output to create a more visually appealing tree
        lines = result.stdout.strip().split("\n")

        # Build a tree structure
        tree: dict[str, dict] = {}
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Remove leading ./
            if line.startswith("./"):
                line = line[2:]
            elif line == ".":
                continue

            parts = line.split("/")
            current = tree
            for part in parts[:-1]:  # Process directories
                if part not in current:
                    current[part] = {}
                current = current[part]

            # Add the leaf (file or directory)
            leaf = parts[-1]
            if leaf:  # Skip empty names
                current[leaf] = {}

        # Convert the tree structure to text
        lines = []

        def _build_tree_text(node, prefix="", is_last=True, lines_list=None):
            if lines_list is None:
                lines_list = []

            items = list(node.items())
            if not items:
                return lines_list

            for i, (name, children) in enumerate(items):
                is_last_item = i == len(items) - 1

                # Add the current line
                if prefix:
                    line = f"{prefix}{'└─ ' if is_last_item else '├─ '}{name}"
                else:
                    line = name
                lines_list.append(line)

                # Process children with proper indentation
                if children:
                    new_prefix = f"{prefix}{'   ' if is_last_item else '│  '}"
                    _build_tree_text(children, new_prefix, is_last_item, lines_list)

            return lines_list

        # Generate the tree text
        tree_lines = _build_tree_text(tree)
        tree_lines.insert(0, ".")  # Add root

        # Limit the number of entries if needed
        if len(tree_lines) > MAX_FILE_TREE_ENTRIES:
            if get_debug():
                console.print(
                    f"[yellow]Limiting file tree from {len(tree_lines)} to {MAX_FILE_TREE_ENTRIES} entries[/yellow]"
                )
            truncated_lines = tree_lines[:MAX_FILE_TREE_ENTRIES]
            truncated_lines.append(
                f"... ({len(tree_lines) - MAX_FILE_TREE_ENTRIES} more entries omitted)"
            )
            tree_lines = truncated_lines

        tree_text = "\n".join(tree_lines)

        if get_debug():
            console.print(
                f"[info]Generated file tree with {len(tree_lines)} entries[/info]"
            )

        return tree_text

    except Exception as e:
        if get_debug():
            console.print(
                f"[yellow]Error generating file tree: {str(e)}[/yellow]"
            )
        return ""