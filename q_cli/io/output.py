"""Output handling for q_cli."""

import os
from rich.console import Console
from rich.theme import Theme


def setup_console() -> Console:
    """Set up and configure the Rich console for output."""
    # Custom theme for the console
    custom_theme = Theme(
        {
            "info": "dim cyan",
            "warning": "magenta",
            "error": "bold red",
            "prompt": "orange1",
            "subdued": "dim dim",
        }
    )

    # Initialize Rich console
    return Console(theme=custom_theme)


def save_response_to_file(response: str, file_path: str, console: Console) -> bool:
    """
    Save the last response from the model to a file.

    Args:
        response: The text response to save
        file_path: The path where the file should be saved
        console: Console instance for output

    Returns:
        True if successfully saved, False otherwise
    """
    try:
        # Ensure the directory exists
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)

        # Write the response to the file
        with open(file_path, "w") as f:
            f.write(response)
        return True
    except Exception as e:
        console.print(f"[bold red]Error saving file: {e}[/bold red]")
        return False
