"""Web utilities for fetching content from URLs."""

import re
import requests
from typing import Tuple, List, Optional, Dict
from rich.console import Console
from bs4 import BeautifulSoup
from q_cli.utils.constants import DEBUG

# Define the special formats for web content fetching
URL_MARKER_START = "FETCH_URL:"
URL_MARKER_END = ">>"


def extract_urls_from_response(response: str) -> List[Tuple[str, str, int, bool]]:
    """
    Extract URLs that are marked for fetching in the model's response.
    
    Formats supported: 
    - FETCH_URL: https://example.com>> (legacy format)
    - ```FETCH_URL: https://example.com``` (new code block format)
    
    Args:
        response: The model's response text
    
    Returns:
        List of tuples containing (original_marker, url, position, is_for_model)
    """
    matches = []
    
    # Pattern 1: Legacy format with markers (still supported)
    legacy_pattern = re.compile(f"{re.escape(URL_MARKER_START)}(.*?){re.escape(URL_MARKER_END)}")
    
    for match in legacy_pattern.finditer(response):
        full_match = match.group(0)  # The entire marker
        url = match.group(1).strip()  # Just the URL part
        position = match.start()
        matches.append((full_match, url, position, False))
    
    # Pattern 2: New code block format
    # This pattern matches ```FETCH_URL: url```
    # We need to be more careful with this pattern as it might include whitespace and newlines
    code_block_pattern = re.compile(r"```FETCH_URL:[\s\n]*(.*?)[\s\n]*```", re.DOTALL)
    
    for match in code_block_pattern.finditer(response):
        full_match = match.group(0)  # The entire code block
        url = match.group(1).strip()  # Just the URL part
        position = match.start()
        
        # Check if this is inside a nested code block
        text_before = response[:position]
        code_block_markers = text_before.count("```")
        is_nested = code_block_markers % 2 == 1
        
        # Only process if it's not nested inside another code block
        if not is_nested:
            matches.append((full_match, url, position, False))
    
    return matches


def fetch_url_content(url: str, console: Console, for_model: bool = False) -> Optional[str]:
    """
    Fetch content from a URL.
    
    Args:
        url: The URL to fetch
        console: Console for output
        for_model: Whether the content is meant for the model (True) or user display (False)
    
    Returns:
        The content of the URL, or None if there was an error
    """
    try:
        console.print(f"[info]Fetching content from {url}...[/info]")
        if DEBUG:
            console.print(f"[yellow]DEBUG: Requesting URL {url}[/yellow]")
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raise exception for HTTP errors
        
        # Check content type to format appropriately
        content_type = response.headers.get('Content-Type', '')
        
        if for_model:
            # For model consumption, provide a more processed version
            if 'text/html' in content_type:
                # Parse HTML and extract meaningful text
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.extract()
                    
                # Get text and clean it up
                text = soup.get_text(separator='\n')
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                text = '\n'.join(lines)
                
                # Truncate if too long
                if len(text) > 15000:
                    text = text[:15000] + "\n\n[Content truncated due to length]"
                
                return f"Content from {url}:\n{text}"
            
            elif 'application/json' in content_type:
                # For JSON, provide the raw JSON for the model
                return f"JSON from {url}:\n{response.text}"
            
            else:
                # For other content types, return as text
                text = response.text
                if len(text) > 15000:
                    text = text[:15000] + "\n\n[Content truncated due to length]"
                return f"Content from {url}:\n{text}"
        else:
            # For user display, format nicely with a brief summary instead of raw content
            if 'application/json' in content_type:
                # For JSON, just indicate it was fetched but don't show raw content
                return f"[info]Successfully fetched JSON content from {url}[/info]"
            elif 'text/html' in content_type:
                # For HTML, just indicate it was fetched but don't show raw content
                return f"[info]Successfully fetched HTML content from {url}[/info]"
            else:
                # For other content types, just indicate it was fetched
                content_type_info = content_type.split(';')[0] if content_type else "unknown"
                return f"[info]Successfully fetched content ({content_type_info}) from {url}[/info]"
            
    except requests.RequestException as e:
        error_msg = f"Error fetching URL {url}: {str(e)}"
        console.print(f"[error]{error_msg}[/error]")
        return f"[Failed to fetch: {error_msg}]" if for_model else None


def process_urls_in_response(
    response: str, 
    console: Console
) -> Tuple[str, Dict[str, str]]:
    """
    Process a response from the model, fetching any URLs.
    
    - For URLs (<<FETCH_URL:...>>), replace markers with content in the response
    
    Args:
        response: The model's response text
        console: Console for output
    
    Returns:
        Tuple containing:
        - Processed response with URL content for user display
        - Dictionary of URL content fetched for model context (for backward compatibility)
    """
    # Extract all URL markers
    url_matches = extract_urls_from_response(response)
    
    if not url_matches:
        return response, {}
    
    # Dictionary to hold content fetched for model (kept for backward compatibility)
    model_url_content = {}
    processed_response = response
    
    # Process in reverse order to avoid position changes
    for marker, url, position, _ in sorted(
        url_matches, key=lambda x: x[2], reverse=True
    ):
        # We'll fetch content with different formatting based on whether the model needs it
        # False for user display, True for model context
        content_for_user = fetch_url_content(url, console, for_model=False)
        content_for_model = fetch_url_content(url, console, for_model=True)
        
        if content_for_user and content_for_model:
            # Insert content indicator for user display (simply remove the marker)
            # We don't want to insert the actual content in the response
            processed_response = processed_response.replace(marker, "", 1)
            
            # Display a simple confirmation message to the user
            console.print(content_for_user)
            # Save content for model context
            model_url_content[url] = content_for_model
        else:
            # If fetching failed, retain the error message in the response for the model
            error_message = f"[Failed to fetch content from {url}]"
            processed_response = processed_response.replace(marker, error_message, 1)
            
            # Also display the error to the user
            console.print(f"[error]{error_message}[/error]")
            
            # Store the error in the model_url_content dictionary so it will be sent to the model
            model_url_content[url] = f"Error fetching content from {url}. The URL could not be accessed or returned an error."
    
    return processed_response, model_url_content