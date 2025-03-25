"""Helper functions used throughout the q_cli package."""

import os
import re
import requests
from typing import Dict, List, Tuple

from rich.console import Console
from rich.markdown import Markdown

from q_cli.utils.constants import SENSITIVE_PATTERNS, REDACTED_TEXT, DEBUG
from q_cli import __version__

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
        return [int(part) for part in version_str.split('.')]
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


def check_for_updates() -> Tuple[bool, str]:
    """
    Check if a newer version of the q tool is available on GitHub.

    Returns:
        Tuple containing:
        - Boolean indicating if an update is available
        - Latest version string if update is available, otherwise empty string
    """
    try:
        # Fetch the latest version from GitHub's raw content
        response = requests.get(
            "https://raw.githubusercontent.com/transparentlyai/q/main/q_cli/__init__.py",
            timeout=2  # Short timeout to prevent startup delay
        )
        response.raise_for_status()

        # Extract version using regex
        pattern = r'__version__\s*=\s*["\']([^"\']+)["\']'
        version_match = re.search(pattern, response.text)
        if version_match:
            github_version = version_match.group(1)
            current_version = __version__
            
            # Use console for debug output if available
            from rich.console import Console
            Console().print(f"[dim]DEBUG: Current version: {current_version}, GitHub version: {github_version}[/dim]") if DEBUG else None
            
            # Check if GitHub version is newer
            if is_newer_version(github_version, current_version):
                return True, github_version
    except Exception as e:
        # Silently fail on any error - don't disrupt the user experience
        if DEBUG:
            from rich.console import Console
            Console().print(f"[yellow]DEBUG: Error checking for updates: {str(e)}[/yellow]")
        pass

    return False, ""


def handle_api_error(e: Exception, console: Console) -> None:
    """Handle errors from the Q API in a consistent way."""
    import anthropic
    import os
    import sys

    if isinstance(e, anthropic.APIStatusError):
        if e.status_code == 401:
            console.print(
                "[bold red]Authentication error: Your API key appears to be invalid. Please check your API key.[/bold red]"
            )
        else:
            console.print(
                f"[bold red]Error communicating with Q (Status {e.status_code}): {e.message}[/bold red]"
            )
    elif isinstance(e, anthropic.APIConnectionError):
        console.print(
            "[bold red]Connection error: Could not connect to Anthropic API. Please check your internet connection.[/bold red]"
        )
    elif isinstance(e, anthropic.APITimeoutError):
        console.print(
            "[bold red]Timeout error: The request to Anthropic API timed out.[/bold red]"
        )
    else:
        console.print(f"[bold red]Error communicating with Q: {e}[/bold red]")

    if os.environ.get("Q_DEBUG"):
        console.print(f"[bold red]Error details: {e}[/bold red]")

    sys.exit(1)
