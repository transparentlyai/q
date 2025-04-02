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


def validate_config(config_vars: Dict[str, str], console: Console) -> None:
    """
    Validate configuration variables for consistency and correctness.
    
    Args:
        config_vars: Dictionary of configuration variables
        console: Console instance for output
        
    Raises:
        ValueError: If configuration is invalid
    """
    from q_cli.utils.constants import SUPPORTED_PROVIDERS
    
    # Check if provider is specified and valid
    if "PROVIDER" in config_vars:
        provider = config_vars["PROVIDER"].lower()
        if provider not in SUPPORTED_PROVIDERS:
            allowed = ", ".join(sorted(SUPPORTED_PROVIDERS))
            error_msg = f"Invalid provider '{provider}' in config. Supported providers: {allowed}"
            console.print(f"[bold red]Error: {error_msg}[/bold red]")
            raise ValueError(error_msg)
            
        # Check for required provider-specific settings
        if provider == "vertexai":
            # VertexAI requires project ID and location
            project_id = config_vars.get("VERTEXAI_PROJECT") or config_vars.get("VERTEX_PROJECT")
            if not project_id:
                console.print("[bold yellow]Warning: VERTEXAI_PROJECT not set in config file (required for VertexAI)[/bold yellow]")
                
            location = config_vars.get("VERTEXAI_LOCATION") or config_vars.get("VERTEX_LOCATION")
            if not location:
                console.print("[bold yellow]Warning: VERTEXAI_LOCATION not set in config file (required for VertexAI)[/bold yellow]")
        
        # Check if provider has API key
        api_key_var = f"{provider.upper()}_API_KEY"
        if api_key_var not in config_vars or not config_vars[api_key_var]:
            console.print(f"[bold yellow]Warning: {api_key_var} not set in config file[/bold yellow]")
    
    # Check for environment variables that might conflict with config
    for provider in SUPPORTED_PROVIDERS:
        env_key = f"{provider.upper()}_API_KEY"
        config_key = env_key
        
        if env_key in os.environ and config_key in config_vars:
            if get_debug():
                console.print(f"[yellow]Note: {env_key} found in both environment and config file. Environment variable takes precedence.[/yellow]")


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
    # For use with multiple providers
    provider_api_keys = {}

    # Find example_config.conf in different possible locations
    # First try the package directory
    package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_root = os.path.dirname(package_dir)

    # Set up possible locations to find example_config.conf
    possible_locations = [
        os.path.join(repo_root, "example_config.conf"),  # Repository root
        os.path.join(
            os.path.dirname(sys.executable), "example_config.conf"
        ),  # Next to Python executable
        os.path.join(package_dir, "example_config.conf"),  # q_cli package directory
        os.path.join(
            os.path.dirname(__file__), "..", "example_config.conf"
        ),  # Relative to this file
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
                            
                            # Strip any inline comments (anything after a # that's not quoted)
                            if "#" in value and not value.startswith('"') and not value.startswith("'"):
                                value = value.split("#", 1)[0].strip()
                            
                            # Expand environment variables in value
                            if "$" in value:
                                value = expand_env_vars(value)

                            # Store in config vars
                            config_vars[key] = value
                            
                            # Debug output for config settings when debug is enabled
                            debug_enabled = get_debug()
                            if debug_enabled:
                                if key.endswith("API_KEY"):
                                    console.print(f"Loaded {key}={value[:5]}... from config file")
                                else:
                                    console.print(f"Loaded {key}={value} from config file")
                                
                            # Make sure to set VERTEXAI_LOCATION in the environment if found in config
                            if key == "VERTEXAI_LOCATION" and value:
                                os.environ["VERTEXAI_LOCATION"] = value
                                os.environ["VERTEX_LOCATION"] = value

                            # Check for API keys for various providers
                            if key == "ANTHROPIC_API_KEY":
                                provider_api_keys["anthropic"] = value
                                if not api_key:  # For backward compatibility
                                    api_key = value
                            elif key == "VERTEXAI_API_KEY":
                                provider_api_keys["vertexai"] = value
                            elif key == "GROQ_API_KEY":
                                provider_api_keys["groq"] = value
                            elif key == "API_KEY" and not api_key:  # Generic API key
                                api_key = value
                        # Check for API key (assuming it's just the key on a line by itself)
                        elif (
                            not api_key and len(line) > 20
                        ):  # Simple validation for API key-like string
                            if line.startswith(
                                "sk-ant-api"
                            ):  # Strict validation for Anthropic v1 API key format
                                api_key = line
                                provider_api_keys["anthropic"] = line
        except Exception as e:
            console.print(f"Warning: Error reading config file: {e}", style="warning")
    else:
        # If config file doesn't exist, create a base one with default settings
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

            # Always use example config if it exists
            if example_config_path and os.path.exists(example_config_path):
                with open(example_config_path, "r") as src, open(
                    CONFIG_PATH, "w"
                ) as dest:
                    dest.write(src.read())
                console.print(
                    f"[green]Created config file at {CONFIG_PATH} using example template.[/green]"
                )
            else:
                # No example config found - this is an error condition
                console.print(
                    f"[red]Error: Could not find example_config.conf in any expected location.[/red]"
                )
                console.print(
                    f"[yellow]This is likely an installation issue. Please report this bug.[/yellow]"
                )

            console.print(
                "Make sure the appropriate API key is set either in the config file or as an environment variable like ANTHROPIC_API_KEY, VERTEXAI_API_KEY, GROQ_API_KEY, or OPENAI_API_KEY.",
                style="info",
            )
        except Exception as e:
            console.print(f"[red]Error creating config file: {e}[/red]")
            console.print(
                f"You can manually create one at {CONFIG_PATH}",
                style="info",
            )

    # Store provider API keys in config_vars
    for provider, key in provider_api_keys.items():
        config_vars[f"{provider.upper()}_API_KEY"] = key
    
    # Store provider keys in a format that can be accessed programmatically
    config_vars["PROVIDER_API_KEYS"] = ",".join([f"{p}:{k}" for p, k in provider_api_keys.items()])
    
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


def update_config_provider(new_provider: str, console: Console, model: str = None) -> bool:
    """
    Update the configuration file with a new provider and optionally a new model.
    Creates a backup of the config file before making changes.
    
    Args:
        new_provider: The new provider to set as default
        console: Console instance for output
        model: Optional model to set as the provider's default model
        
    Returns:
        True if the update was successful, False otherwise
    """
    try:
        if not os.path.exists(CONFIG_PATH):
            console.print(f"[yellow]Config file not found at {CONFIG_PATH}[/yellow]")
            return False
        
        # Create a backup of the current config file
        import shutil
        from datetime import datetime
        
        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = f"{CONFIG_PATH}.{timestamp}.bak"
        
        # Make the backup
        try:
            shutil.copy2(CONFIG_PATH, backup_path)
            if get_debug():
                console.print(f"[green]Created config backup at {backup_path}[/green]")
        except Exception as backup_error:
            console.print(f"[yellow]Warning: Failed to create config backup: {str(backup_error)}[/yellow]")
            # Continue even if backup fails - user can proceed
            
        # Read the current config file
        with open(CONFIG_PATH, "r") as f:
            lines = f.readlines()
            
        # Check if PROVIDER is already in the config
        provider_found = False
        for i, line in enumerate(lines):
            if line.strip().startswith("PROVIDER="):
                # Update the provider
                lines[i] = f"PROVIDER={new_provider}\n"
                provider_found = True
                break
                
        # If PROVIDER wasn't found, add it to the beginning of the file
        if not provider_found:
            # Find a good position to insert - after any comments at the top
            insert_position = 0
            for i, line in enumerate(lines):
                if line.strip().startswith("#") or not line.strip():
                    insert_position = i + 1
                else:
                    break
                    
            lines.insert(insert_position, f"PROVIDER={new_provider}\n")
            
        # If model is provided, update the provider-specific model setting
        if model:
            model_key = f"{new_provider.upper()}_MODEL"
            model_found = False
            
            # Check if the model setting already exists
            for i, line in enumerate(lines):
                if line.strip().startswith(f"{model_key}="):
                    # Update the model
                    lines[i] = f"{model_key}={model}\n"
                    model_found = True
                    break
                    
            # If model setting wasn't found, add it after the provider setting
            if not model_found:
                provider_line_index = -1
                for i, line in enumerate(lines):
                    if line.strip().startswith("PROVIDER="):
                        provider_line_index = i
                        break
                
                # Insert after the provider line if found, or at the beginning
                if provider_line_index >= 0:
                    lines.insert(provider_line_index + 1, f"{model_key}={model}\n")
                else:
                    lines.insert(0, f"{model_key}={model}\n")
            
        # Write the updated config back to the file
        with open(CONFIG_PATH, "w") as f:
            f.writelines(lines)
            
        if get_debug():
            console.print(f"[green]Updated config file to use provider: {new_provider}[/green]")
        else:
            console.print(f"[dim]Config file updated (backup created)[/dim]")
            
        return True
        
    except Exception as e:
        console.print(f"[red]Error updating config file: {str(e)}[/red]")
        return False


def build_context(
    args, config_context: str, console: Console, config_vars: Dict[str, str] = None
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
    # Import provider-specific constants
    from q_cli.utils.constants import (
        DEFAULT_PROVIDER,
        ANTHROPIC_MAX_CONTEXT_TOKENS,
        VERTEXAI_MAX_CONTEXT_TOKENS,
        GROQ_MAX_CONTEXT_TOKENS,
        OPENAI_MAX_CONTEXT_TOKENS,
        DEFAULT_MAX_CONTEXT_TOKENS,
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
    elif provider.lower() == "anthropic":
        # Config value or default
        anthropic_max = config_vars.get("ANTHROPIC_MAX_CONTEXT_TOKENS")
        if anthropic_max and "#" in anthropic_max:
            # Remove inline comments from the value
            anthropic_max = anthropic_max.split("#")[0].strip()
        max_tokens = int(anthropic_max or ANTHROPIC_MAX_CONTEXT_TOKENS)
    elif provider.lower() == "vertexai":
        vertex_max = config_vars.get("VERTEXAI_MAX_CONTEXT_TOKENS")
        if vertex_max and "#" in vertex_max:
            # Remove inline comments from the value
            vertex_max = vertex_max.split("#")[0].strip()
        max_tokens = int(vertex_max or VERTEXAI_MAX_CONTEXT_TOKENS)
        if get_debug():
            console.print(f"[info]Using VertexAI context limit: {max_tokens} tokens[/info]")
    elif provider.lower() == "groq":
        groq_max = config_vars.get("GROQ_MAX_CONTEXT_TOKENS")
        if groq_max and "#" in groq_max:
            # Remove inline comments from the value
            groq_max = groq_max.split("#")[0].strip()
        max_tokens = int(groq_max or GROQ_MAX_CONTEXT_TOKENS)
    elif provider.lower() == "openai":
        openai_max = config_vars.get("OPENAI_MAX_CONTEXT_TOKENS")
        if openai_max and "#" in openai_max:
            # Remove inline comments from the value
            openai_max = openai_max.split("#")[0].strip()
        max_tokens = int(openai_max or OPENAI_MAX_CONTEXT_TOKENS)
    else:
        default_max = config_vars.get("MAX_CONTEXT_TOKENS")
        if default_max and "#" in default_max:
            # Remove inline comments from the value
            default_max = default_max.split("#")[0].strip()
        max_tokens = int(default_max or DEFAULT_MAX_CONTEXT_TOKENS)
    
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
                    "[yellow]get_debug(): 'tree' command not found, using fallback method[/yellow]"
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
                    f"[yellow]get_debug(): Error generating file tree: {result.stderr}[/yellow]"
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
                    f"[yellow]get_debug(): Limiting file tree from {len(tree_lines)} to {MAX_FILE_TREE_ENTRIES} entries[/yellow]"
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
                f"[yellow]get_debug(): Error generating file tree: {str(e)}[/yellow]"
            )
        return ""
