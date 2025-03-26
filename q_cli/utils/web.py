"""Web utilities for fetching content from URLs."""

import re
import requests
from typing import Tuple, List, Optional, Dict
from rich.console import Console
from bs4 import BeautifulSoup
from q_cli.utils.constants import DEBUG

# Define the special format for web content fetching
URL_BLOCK_MARKER = "Q:COMMAND type=\"fetch\""  # Code block format


def extract_urls_from_response(response: str) -> List[Tuple[str, str, int, bool]]:
    """
    Extract URLs that are marked for fetching in the model's response.

    Format supported:
    - <Q:COMMAND type="fetch">
      https://example.com
      </Q:COMMAND>

    Args:
        response: The model's response text

    Returns:
        List of tuples containing (original_marker, url, position, is_for_model)
    """
    matches = []

    # Pattern: XML-like format
    # This pattern matches <Q:COMMAND type="fetch">url</Q:COMMAND>
    code_block_pattern = re.compile(
        r"<" + re.escape(URL_BLOCK_MARKER) + r">\s*(.*?)\s*</Q:COMMAND>", re.DOTALL
    )

    for match in code_block_pattern.finditer(response):
        full_match = match.group(0)  # The entire tag block
        url = match.group(1).strip()  # Just the URL part
        position = match.start()

        # For XML-like tags we don't need to check for nested blocks
        matches.append((full_match, url, position, False))

    return matches


def process_urls_in_response(
    response: str, console: Console, show_errors: bool = True
) -> Tuple[str, Dict[str, str], bool]:
    """
    Process a response from the model, fetching any URLs.

    - For URLs, replace markers with content in the response

    Args:
        response: The model's response text
        console: Console for output
        show_errors: Whether to display error messages to the user

    Returns:
        Tuple containing:
        - Processed response with URL content for user display
        - Dictionary of URL content fetched for model context
        - Boolean indicating if any errors occurred
    """
    # Extract all URL markers
    url_matches = extract_urls_from_response(response)

    if not url_matches:
        return response, {}, False

    # Dictionary to hold content fetched for model
    model_url_content = {}
    processed_response = response
    has_error = False

    # Process in reverse order to avoid position changes
    for marker, url, position, _ in sorted(
        url_matches, key=lambda x: x[2], reverse=True
    ):
        try:
            # Show fetching message without interrupt hint
            console.print(f"[dim]Fetching {url}[/dim]")

            # Show additional debug info if in DEBUG mode
            if DEBUG:
                console.print(f"[yellow]DEBUG: Requesting URL {url}[/yellow]")

            try:
                # Fetch the URL once
                response_obj = requests.get(url, timeout=10)
                response_obj.raise_for_status()  # Raise exception for HTTP errors
            except KeyboardInterrupt:
                # Handle Ctrl+C during URL fetch
                console.print(
                    f"\n[bold red]URL fetch interrupted by user: {url}[/bold red]"
                )
                # Add this error to our results and continue with the next URL
                has_error = True
                # Add STOP message for operations
                model_url_content[url] = (
                    "STOP. The operation was cancelled by user. Do not proceed with any additional commands or operations. Wait for new instructions from the user."
                )
                # Skip to the next URL rather than exiting completely
                processed_response = processed_response.replace(marker, "", 1)
                continue

            # Check content type to format appropriately
            content_type = response_obj.headers.get("Content-Type", "")

            # Format for user display
            if "application/json" in content_type:
                content_for_user = (
                    f"[info]Successfully fetched JSON content from {url}[/info]"
                )
            elif "text/html" in content_type:
                content_for_user = (
                    f"[info]Successfully fetched HTML content from {url}[/info]"
                )
            else:
                content_type_info = (
                    content_type.split(";")[0] if content_type else "unknown"
                )
                content_for_user = f"[info]Successfully fetched content ({content_type_info}) from {url}[/info]"

            # Format for model
            if "text/html" in content_type:
                # Parse HTML and extract meaningful text
                soup = BeautifulSoup(response_obj.text, "html.parser")

                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.extract()

                # Get text and clean it up
                text = soup.get_text(separator="\n")
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                text = "\n".join(lines)

                # Truncate if too long
                if len(text) > 15000:
                    text = text[:15000] + "\n\n[Content truncated due to length]"

                content_for_model = f"Content from {url}:\n{text}"

            elif "application/json" in content_type:
                # For JSON, provide the raw JSON for the model
                content_for_model = f"JSON from {url}:\n{response_obj.text}"

            else:
                # For other content types, return as text
                text = response_obj.text
                if len(text) > 15000:
                    text = text[:15000] + "\n\n[Content truncated due to length]"
                content_for_model = f"Content from {url}:\n{text}"

            # Remove the code block completely from the response
            processed_response = processed_response.replace(marker, "", 1)

            # Only display a confirmation message in DEBUG mode
            if DEBUG:
                console.print(content_for_user)
            # Save content for model context
            model_url_content[url] = content_for_model

        except requests.RequestException as e:
            # If fetching failed, track the error
            has_error = True
            error_msg = f"Error fetching URL {url}: {str(e)}"

            # Only show debug info
            if DEBUG:
                console.print(f"[yellow]DEBUG: {error_msg}[/yellow]")

            # Remove the code block completely from the response
            processed_response = processed_response.replace(marker, "", 1)

            # Store the error in the model_url_content dictionary so it will be sent to the model
            model_url_content[url] = (
                f"Error fetching content from {url}. The URL could not be accessed or returned an error."
            )

    # We no longer show errors here - they're handled at the higher level in conversation.py

    # Clean up any resulting empty lines from multiple consecutive newlines
    processed_response = re.sub(r"\n{3,}", "\n\n", processed_response)

    # Clean up any empty code blocks that might remain after URL processing
    processed_response = re.sub(r"```\s*```", "", processed_response)

    # Handle edge case of code blocks with just whitespace
    processed_response = re.sub(r"```\s+```", "", processed_response)

    return processed_response, model_url_content, has_error
