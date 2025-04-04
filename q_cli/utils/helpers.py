"""Helper functions used throughout the q_cli package."""

import os
import re
from typing import Dict, List, Tuple, Optional

from rich.console import Console
from rich.markdown import Markdown

from q_cli.utils.constants import SENSITIVE_PATTERNS, REDACTED_TEXT, get_debug

# Type definitions for better code clarity
Message = Dict[str, str]
Conversation = List[Message]


def contains_sensitive_info(text: str) -> bool:
    """Check if text contains potentially sensitive information."""
    text_lower = text.lower()
    return any(pattern in text_lower for pattern in SENSITIVE_PATTERNS)


def format_markdown(text: str) -> Markdown:
    """
    Format markdown text into Rich-formatted text for terminal display.

    Args:
        text: The markdown text to format

    Returns:
        A Rich Markdown object that can be printed to the console
    """
    return Markdown(text)


def clean_operation_codeblocks(text: str) -> str:
    """
    Clean up markdown code blocks that surround operation results.
    Sometimes models output operations enclosed in triple backticks.
    This function ONLY removes triple backticks when they surround the entire operation.
    It does NOT remove code blocks within explanations or code examples.
    
    Args:
        text: The operation text that might be surrounded by unnecessary code blocks
        
    Returns:
        Cleaned text with operation-surrounding triple backticks removed
    """
    # Check if the entire text is a code block
    # This means it starts with triple backticks (possibly with a language identifier)
    # and ends with triple backticks
    text = text.strip()
    
    # Pattern for starting code block: "```" possibly followed by a language identifier
    start_pattern = r"^\s*```\w*\s*\n"
    # Pattern for ending code block: "```" at the end of the text
    end_pattern = r"\n\s*```\s*$"
    
    # Only clean if the entire content is enclosed in a code block
    if re.match(start_pattern, text) and re.search(end_pattern, text):
        # Remove the starting code block marker and language identifier
        text = re.sub(start_pattern, "", text)
        # Remove the ending code block marker
        text = re.sub(end_pattern, "", text)
    
    return text


def expand_env_vars(text: str) -> str:
    """Replace environment variables in text."""
    if "$" not in text:
        return text

    # Handle ${VAR} format
    text = re.sub(r"\${(\w+)}", lambda m: os.environ.get(m.group(1), ""), text)
    # Handle $VAR format
    text = re.sub(r"\$(\w+)", lambda m: os.environ.get(m.group(1), ""), text)
    return text


def sanitize_context(context: str, console: Console) -> str:
    """Ensure no sensitive information is present in the context."""
    if not context:
        return ""

    lines = context.split("\n")
    for i, line in enumerate(lines):
        # First expand environment variables in the line
        lines[i] = expand_env_vars(line)

        # Then check for sensitive information
        if contains_sensitive_info(lines[i]):
            console.print(
                "Warning: Potentially sensitive information found in context. Redacting.",
                style="warning",
            )
            lines[i] = REDACTED_TEXT

    return "\n".join(lines)


def parse_version(version_str: str) -> List[int]:
    """
    Parse a version string into a list of integers.
    Handles version strings like "0.9.0.64" by splitting on dots.
    """
    try:
        return [int(part) for part in version_str.split(".")]
    except ValueError:
        # If conversion fails, fall back to a safe default
        return [0, 0, 0]


def is_newer_version(version1: str, version2: str) -> bool:
    """
    Check if version1 is newer than version2.
    Returns True if version1 > version2, False otherwise.
    """
    # Handle empty or None values by treating them as older
    if not version1:
        return False
    if not version2:
        return True

    v1_parts = parse_version(version1)
    v2_parts = parse_version(version2)

    # Compare each part in order
    for i in range(max(len(v1_parts), len(v2_parts))):
        v1_part = v1_parts[i] if i < len(v1_parts) else 0
        v2_part = v2_parts[i] if i < len(v2_parts) else 0

        if v1_part > v2_part:
            return True
        elif v1_part < v2_part:
            return False

    # If we get here, versions are identical
    return False


def check_for_updates(console: Optional[Console] = None) -> Tuple[bool, str]:
    """
    Check if a newer version of the q tool is available on GitHub.

    Returns:
        Tuple containing:
        - Boolean indicating if an update is available
        - Latest version string if update is available, otherwise empty string
    """
    try:
        # Lazy import to avoid loading these modules during startup
        import requests
        import re
        from q_cli import __version__
        
        # Fetch the latest version from GitHub's raw content
        response = requests.get(
            "https://raw.githubusercontent.com/transparentlyai/q/main/q_cli/__init__.py",
            timeout=2,  # Short timeout to prevent startup delay
        )
        response.raise_for_status()

        # Extract version using regex
        pattern = r'__version__\s*=\s*["\']([^"\']+)["\']'
        version_match = re.search(pattern, response.text)
        if version_match:
            github_version = version_match.group(1)
            current_version = __version__

            # Use console for debug output if debug mode is enabled
            if get_debug() and console:
                console.print(
                    f"[dim]Current version: {current_version}, GitHub version: {github_version}[/dim]"
                )

            # Check if GitHub version is newer
            if is_newer_version(github_version, current_version):
                return True, github_version
    except Exception as e:
        # Silently fail on any error - don't disrupt the user experience
        if get_debug() and console:
            console.print(
                f"[yellow]Error checking for updates: {str(e)}[/yellow]"
            )

    return False, ""


def handle_api_error(
    e: Exception, console: Console, exit_on_error: bool = True
) -> bool:
    """
    Handle errors from LLM providers in a consistent way.
    Works with errors from either litellm or direct provider APIs.

    Args:
        e: The exception that occurred
        console: Console for output
        exit_on_error: Whether to exit the program on error

    Returns:
        True if error is a rate limit error that can be retried, False otherwise
    """
    import os
    import sys
    # Already imported get_debug at top of file
    
    # Lazy imports to reduce startup time
    import litellm

    # LiteLLM is the only API we need
    has_anthropic = False

    is_rate_limit_error = False

    # Handle LiteLLM-specific errors first (preferred path)
    if isinstance(e, litellm.exceptions.BadRequestError):
        error_str = str(e)
        # Special handling for VertexAI permission errors in BadRequestError
        if "Permission" in error_str and "denied" in error_str and ("vertexai" in error_str.lower() or "aiplatform" in error_str.lower()):
            console.print("[bold red]VertexAI Permission Denied Error[/bold red]")
            console.print("\n[yellow]This typically means:[/yellow]")
            console.print("1. Your service account doesn't have sufficient permissions")
            console.print("2. Required IAM role: 'roles/aiplatform.user' or 'aiplatform.admin'")
            console.print("3. Make sure the Vertex AI API is enabled in your GCP project")
            console.print("4. Check if the model is available in your selected region")
            console.print(f"\n[dim]Original error: {error_str}[/dim]")
        else:
            console.print(
                f"[bold red]Bad request error: {error_str}[/bold red]"
            )
    elif isinstance(e, litellm.exceptions.RateLimitError):
        console.print(
            f"[bold yellow]Rate limit exceeded: {str(e)}[/bold yellow]"
        )
        is_rate_limit_error = True
        
        # Only exit if requested
        if not exit_on_error:
            console.print(
                "[yellow]Waiting to retry after rate limit cooldown...[/yellow]"
            )
            return is_rate_limit_error
    elif isinstance(e, litellm.exceptions.AuthenticationError):
        error_str = str(e)
        if "vertex" in error_str.lower() or "google" in error_str.lower():
            console.print("[bold red]VertexAI Authentication Error[/bold red]")
            console.print("\n[yellow]This could be due to:[/yellow]")
            console.print("1. Invalid or inaccessible service account JSON file")
            console.print("2. Missing required environment variables (VERTEXAI_PROJECT, VERTEXAI_LOCATION)")
            console.print("3. Project ID or location may be incorrect")
            console.print(f"\n[dim]Original error: {error_str}[/dim]")
        else:
            console.print(
                "[bold red]Authentication error: Your API key appears to be invalid. Please check your API key.[/bold red]"
            )
    # Handle content filter errors based on message content
    elif any(term in str(e).lower() for term in ['content filter', 'contentfilter', 'content_filter', 'inappropriate', 'moderation']):
        console.print(
            f"[bold red]Content filter error: {str(e)}[/bold red]"
        )
    elif isinstance(e, litellm.exceptions.APIError):
        if "401" in str(e) or "Unauthorized" in str(e) or "authentication" in str(e).lower():
            console.print(
                "[bold red]Authentication error: Your API key appears to be invalid. Please check your API key.[/bold red]"
            )
        elif "429" in str(e) or "rate" in str(e).lower() or "limit" in str(e).lower():
            console.print(
                f"[bold yellow]Rate limit exceeded: {str(e)}[/bold yellow]"
            )
            is_rate_limit_error = True
            
            # Only exit if requested
            if not exit_on_error:
                console.print(
                    "[yellow]Waiting to retry after rate limit cooldown...[/yellow]"
                )
                return is_rate_limit_error
        # Special handling for VertexAI permission errors
        elif "Permission" in str(e) and "denied" in str(e) and ("vertexai" in str(e).lower() or "aiplatform" in str(e).lower()):
            console.print("[bold red]VertexAI Permission Denied Error[/bold red]")
            console.print("\n[yellow]This typically means:[/yellow]")
            console.print("1. Your service account doesn't have sufficient permissions")
            console.print("2. Required IAM role: 'roles/aiplatform.user' or 'aiplatform.admin'")
            console.print("3. Make sure the Vertex AI API is enabled in your GCP project")
            console.print("4. Check if the model is available in your selected region")
            console.print(f"\n[dim]Original error: {str(e)}[/dim]")
        else:
            console.print(
                f"[bold red]Error communicating with LLM provider: {str(e)}[/bold red]"
            )
    # All provider errors are now handled by litellm
    # Generic fallback for any other error
    else:
        console.print(f"[bold red]Error communicating with LLM provider: {e}[/bold red]")

    if get_debug():
        console.print(f"[bold red]Error details: {e}[/bold red]")

    if exit_on_error:
        sys.exit(1)

    return is_rate_limit_error


def get_working_and_project_dirs() -> str:
    """
    Find both the current working directory and the project root directory.

    The current working directory is where q was started from.
    The project directory is identified by looking for a .Q or .git directory,
    searching upward from the current directory until reaching one directory before
    the user's home directory.

    Returns:
        A formatted string containing both directory paths and a list of all project files.
    """
    # Get the current working directory
    cwd = os.getcwd()

    # Get the user's home directory
    home_dir = os.path.expanduser("~")

    # Get the parent of home directory (we should stop before this)
    home_parent = os.path.dirname(home_dir)

    # Start searching for project root from the current directory
    project_dir = None
    search_dir = cwd

    # Continue searching until we reach one directory before the home directory
    while search_dir:
        # Check if .Q directory exists
        q_dir_path = os.path.join(search_dir, ".Q")
        if os.path.isdir(q_dir_path):
            project_dir = search_dir
            break

        # If not, check for .git directory
        git_dir_path = os.path.join(search_dir, ".git")
        if os.path.isdir(git_dir_path):
            project_dir = search_dir
            break

        # Move up one directory
        parent_dir = os.path.dirname(search_dir)

        # Stop searching if:
        # 1. We've reached the root directory (parent == search_dir)
        # 2. We've reached the parent of home directory
        # 3. We've reached the home directory itself
        if (parent_dir == search_dir or
                search_dir == home_parent or
                search_dir == home_dir):
            break

        search_dir = parent_dir

    # Build the result string
    result = f"Current Working Directory: {cwd}\n"

    if project_dir:
        result += f"Project Root Directory: {project_dir}\n\n"
        result += "Project Files:\n"

        # List all files in the project directory with full paths
        try:
            file_list = []
            for root, _, files in os.walk(project_dir):
                # Skip .git and other hidden directories
                if "/." in root:
                    continue

                for file in files:
                    # Skip hidden files
                    if file.startswith("."):
                        continue

                    file_path = os.path.join(root, file)
                    file_list.append(file_path)

            # Sort the files for consistent output
            file_list.sort()

            # Add the file list to the result
            result += "\n".join(file_list)
        except Exception as e:
            result += f"Error listing project files: {str(e)}"
    else:
        result += "Project Root Directory: Unknown"

    return result


