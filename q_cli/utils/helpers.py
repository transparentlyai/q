"""Helper functions used throughout the q_cli package."""

import os
import re
import requests
from typing import Dict, List, Tuple

from rich.console import Console
from rich.markdown import Markdown

from q_cli.utils.constants import SENSITIVE_PATTERNS, REDACTED_TEXT
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
            latest_version = version_match.group(1)
            current_version = __version__

            # Properly compare version numbers instead of strings
            latest_parts = [int(x) for x in latest_version.split('.')]
            current_parts = [int(x) for x in current_version.split('.')]
            
            # Compare version parts from left to right
            for i in range(max(len(latest_parts), len(current_parts))):
                latest_part = latest_parts[i] if i < len(latest_parts) else 0
                current_part = current_parts[i] if i < len(current_parts) else 0
                
                if latest_part > current_part:
                    return True, latest_version
                elif current_part > latest_part:
                    # Current version is newer than remote (unusual but possible during development)
                    return False, ""
            
            # If we get here, versions are identical
            return False, ""
    except (requests.RequestException, Exception):
        # Silently fail on any error - don't disrupt the user experience
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
                "Authentication error: Your API key appears to be invalid. Please check your API key.",
                style="error",
            )
        else:
            console.print(
                f"Error communicating with Q (Status {e.status_code}): {e.message}",
                style="error",
            )
    elif isinstance(e, anthropic.APIConnectionError):
        console.print(
            "Connection error: Could not connect to Anthropic API. Please check your internet connection.",
            style="error",
        )
    elif isinstance(e, anthropic.APITimeoutError):
        console.print(
            "Timeout error: The request to Anthropic API timed out.", style="error"
        )
    else:
        console.print(f"Error communicating with Q: {e}", style="error")

    if os.environ.get("Q_DEBUG"):
        console.print(f"Error details: {e}", style="error")

    sys.exit(1)
