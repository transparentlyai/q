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
    
    Format: 
    - <<FETCH_URL:https://example.com>> (can appear inside or outside code blocks)
    
    Args:
        response: The model's response text
    
    Returns:
        List of tuples containing (original_marker, url, position, is_for_model)
    """
    # Create a pattern that matches the URL marker, ignoring code block boundaries
    pattern = re.compile(f"{re.escape(URL_MARKER_START)}(.*?){re.escape(URL_MARKER_END)}")
    matches = []
    
    # First pass: find all matches including those in code blocks
    for match in pattern.finditer(response):
        full_match = match.group(0)  # The entire marker
        url = match.group(1).strip()  # Just the URL part
        position = match.start()
        
        # Check if this match is inside a code block by counting ``` before this position
        text_before = response[:position]
        code_block_markers = text_before.count("```")
        
        # If even number of ``` markers, we're outside a code block
        # If odd number of ``` markers, we're inside a code block
        is_inside_code_block = code_block_markers % 2 == 1
        
        # We now accept markers both inside and outside code blocks
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
            # For user display, format nicely with markdown
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
            # Insert content for user display
            processed_response = processed_response.replace(
                marker, 
                f"\n\n{content_for_user}\n\n", 
                1
            )
            # Save content for model context
            model_url_content[url] = content_for_model
        else:
            # If fetching failed, just remove the marker
            processed_response = processed_response.replace(
                marker, 
                f"[Failed to fetch content from {url}]", 
                1
            )
    
    return processed_response, model_url_content