"""Web utilities for fetching content from URLs."""

import re
import requests
from typing import Tuple, List, Optional
from rich.console import Console

# Define the special format for web content fetching
URL_MARKER_START = "<<FETCH_URL:"
URL_MARKER_END = ">>"


def extract_urls_from_response(response: str) -> List[Tuple[str, str, int]]:
    """
    Extract URLs that are marked for fetching in the model's response.
    
    Format: <<FETCH_URL:https://example.com>>
    
    Args:
        response: The model's response text
    
    Returns:
        List of tuples containing (original_marker, url, position)
    """
    pattern = re.compile(f"{re.escape(URL_MARKER_START)}(.*?){re.escape(URL_MARKER_END)}")
    matches = []
    
    for match in pattern.finditer(response):
        full_match = match.group(0)  # The entire marker
        url = match.group(1).strip()  # Just the URL part
        position = match.start()
        matches.append((full_match, url, position))
    
    return matches


def fetch_url_content(url: str, console: Console) -> Optional[str]:
    """
    Fetch content from a URL.
    
    Args:
        url: The URL to fetch
        console: Console for output
    
    Returns:
        The content of the URL, or None if there was an error
    """
    try:
        console.print(f"[info]Fetching content from {url}...[/info]")
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raise exception for HTTP errors
        
        # Check content type to format appropriately
        content_type = response.headers.get('Content-Type', '')
        
        if 'application/json' in content_type:
            # Return formatted JSON
            return f"JSON content from {url}:\n```json\n{response.text}\n```"
        elif 'text/html' in content_type:
            # For HTML, return a simple version with limited length
            text = response.text
            if len(text) > 10000:
                text = text[:10000] + "\n\n[Content truncated due to length]"
            return f"HTML content from {url} (truncated):\n```html\n{text}\n```"
        else:
            # For other content types, return as-is with limited length
            text = response.text
            if len(text) > 10000:
                text = text[:10000] + "\n\n[Content truncated due to length]"
            return f"Content from {url}:\n```\n{text}\n```"
            
    except requests.RequestException as e:
        console.print(f"[error]Error fetching URL {url}: {str(e)}[/error]")
        return None


def process_urls_in_response(response: str, console: Console) -> str:
    """
    Process a response from the model, fetching any URLs and replacing the 
    markers with the fetched content.
    
    Args:
        response: The model's response text
        console: Console for output
    
    Returns:
        The processed response with URL content fetched and inserted
    """
    # Extract all URL markers
    url_matches = extract_urls_from_response(response)
    
    if not url_matches:
        return response
    
    # Process in reverse order to avoid position changes
    for marker, url, _ in sorted(url_matches, key=lambda x: x[2], reverse=True):
        content = fetch_url_content(url, console)
        
        if content:
            # Replace the marker with the fetched content
            response = response.replace(marker, f"\n\n{content}\n\n", 1)
        else:
            # If fetching failed, just remove the marker
            response = response.replace(marker, f"[Failed to fetch content from {url}]", 1)
    
    return response