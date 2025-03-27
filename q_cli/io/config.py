"""Configuration file handling for q_cli."""

import os
import sys
import subprocess
from typing import Dict, Optional, Tuple, List

from rich.console import Console

from q_cli.utils.constants import (
    CONFIG_PATH,
    REDACTED_TEXT,
    DEBUG,
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


def read_config_file(console: Console) -> Tuple[Optional[str], str, Dict[str, str]]:
    """
    Read the configuration file for API key and context.

    Returns:
        Tuple containing:
        - API key (or None if not found)
        - Context string
        - Dictionary of configuration variables
    """
    # Show config file path
    console.print(f"[dim]Using config file: {CONFIG_PATH}[/dim]")
    api_key = None
    config_vars = {}
    context = ""
    context_started = False

    # Find example_config.conf in different possible locations
    # First try the package directory
    package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_root = os.path.dirname(package_dir)

    # Set up possible locations to find example_config.conf
    possible_locations = [
        os.path.join(package_dir, "example_config.conf"),  # q_cli package directory
        os.path.join(
            os.path.dirname(__file__), "..", "example_config.conf"
        ),  # Relative to this file
        os.path.join(
            os.path.dirname(sys.executable), "example_config.conf"
        ),  # Next to Python executable
        # For backwards compatibility, checks repo root last
        os.path.join(repo_root, "example_config.conf"),  # Repository root
    ]

    # Find the first existing config
    example_config_path = None
    for path in possible_locations:
        if os.path.exists(path):
            example_config_path = path
            break

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
            if example_config_path and os.path.exists(example_config_path):
                with open(example_config_path, "r") as src, open(
                    CONFIG_PATH, "w"
                ) as dest:
                    dest.write(src.read())
                console.print(
                    f"[green]Created config file at {CONFIG_PATH} using example template.[/green]"
                )
            else:
                # Create minimal config with default values as fallback
                minimal_config = """# Configuration file for q - AI Command Line Assistant
# Edit this file to customize behavior

# Anthropic API key (recommended to use environment variable)
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
MODEL=claude-3.7-latest

# Command permission settings (JSON arrays)
ALWAYS_APPROVED_COMMANDS=["ls", "pwd", "echo", "date", "whoami", "cat"]
ALWAYS_RESTRICTED_COMMANDS=["sudo", "rm", "mv"]
PROHIBITED_COMMANDS=["rm -rf /", "shutdown", "reboot"]

# Display settings
# INCLUDE_FILE_TREE=true # Uncomment to include file tree in context

#CONTEXT
- Be concise in your answers unless asked for detail
"""
                with open(CONFIG_PATH, "w") as f:
                    f.write(minimal_config)
                console.print(
                    f"[green]Created minimal config file at {CONFIG_PATH}.[/green]"
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


def build_context(
    args, config_context: str, console: Console
) -> Tuple[str, ContextManager]:
    """
    Build the context from config and additional context files using priority-based management.

    Args:
        args: Command line arguments
        config_context: Context from the config file
        console: Console instance for output

    Returns:
        Tuple containing:
        - Combined context string
        - ContextManager instance
    """
    # Initialize context manager with args or default values
    max_tokens = getattr(args, "max_context_tokens", None)
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
            console.print(f"[dim]Loading context file: {file_path}[/dim]")
            file_content = read_context_file(file_path, console)
            if file_content:
                context_manager.add_context(
                    f"Content from {os.path.basename(file_path)}:\n{file_content}",
                    IMPORTANT_PRIORITY,
                    f"File context: {os.path.basename(file_path)}",
                )
            else:
                console.print(f"[yellow]Warning: No content loaded from context file: {file_path}[/yellow]")

    # Add the current directory file tree to the context if enabled (important priority)
    if INCLUDE_FILE_TREE:
        console.print(f"[dim]Generating file tree for current directory...[/dim]")
        file_tree = generate_file_tree(console)
        if file_tree:
            file_count = file_tree.count('\n')
            context_manager.add_context(
                "Current directory file structure:\n```\n" + file_tree + "\n```",
                IMPORTANT_PRIORITY,
                "File tree",
            )
            console.print(f"[dim]Added file tree with {file_count} entries to context[/dim]")
        else:
            console.print("[yellow]Warning: Unable to generate file tree[/yellow]")

    # Check for .Q directory in current working directory
    q_dir_path = os.path.join(os.getcwd(), ".Q")
    if os.path.isdir(q_dir_path):
        console.print(f"[dim]Found project .Q directory[/dim]")
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
                console.print(
                    f"[dim]Added {len(q_files)} files from .Q directory to context[/dim]"
                )
            else:
                console.print(f"[dim]Project .Q directory is empty[/dim]")
        except Exception as e:
            console.print(f"[yellow]Error reading .Q directory: {str(e)}[/yellow]")

    # Check for project.md file inside the .Q directory
    project_md_path = os.path.join(q_dir_path, "project.md")
    if os.path.isdir(q_dir_path) and os.path.isfile(project_md_path):
        console.print(f"[dim]Found project.md file[/dim]")
        try:
            project_content = read_context_file(project_md_path, console)
            if project_content:
                content_length = len(project_content)
                context_manager.add_context(
                    f"Project Information:\n{project_content}",
                    IMPORTANT_PRIORITY,
                    "project.md content",
                )
                console.print(f"[dim]Added project.md ({content_length} chars) to context[/dim]")
            else:
                console.print("[yellow]Warning: Empty project.md file[/yellow]")
        except Exception as e:
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
                if DEBUG:
                    console.print(
                        f"[info]Generated file tree using 'tree' command[/info]"
                    )
                return tree_output
        except FileNotFoundError:
            # Tree command not available, we'll use the fallback method
            if DEBUG:
                console.print(
                    "[yellow]DEBUG: 'tree' command not found, using fallback method[/yellow]"
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
            if DEBUG:
                console.print(
                    f"[yellow]DEBUG: Error generating file tree: {result.stderr}[/yellow]"
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
            if DEBUG:
                console.print(
                    f"[yellow]DEBUG: Limiting file tree from {len(tree_lines)} to {MAX_FILE_TREE_ENTRIES} entries[/yellow]"
                )
            truncated_lines = tree_lines[:MAX_FILE_TREE_ENTRIES]
            truncated_lines.append(
                f"... ({len(tree_lines) - MAX_FILE_TREE_ENTRIES} more entries omitted)"
            )
            tree_lines = truncated_lines

        tree_text = "\n".join(tree_lines)

        if DEBUG:
            console.print(
                f"[info]Generated file tree with {len(tree_lines)} entries[/info]"
            )

        return tree_text

    except Exception as e:
        if DEBUG:
            console.print(
                f"[yellow]DEBUG: Error generating file tree: {str(e)}[/yellow]"
            )
        return ""
