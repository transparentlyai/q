"""Command line argument parsing for q_cli."""

import argparse
import subprocess
import sys
from q_cli import __version__


def update_command():
    """Update q to the latest version from GitHub."""
    try:
        print("Updating q to the latest version...")
        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "git+https://github.com/transparentlyai/q.git",
            ]
        )
        print("Update completed successfully!")
    except subprocess.CalledProcessError as e:
        print(f"Error updating q: {e}")
    sys.exit(0)


def setup_argparse() -> argparse.ArgumentParser:
    """Set up the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        description="Send a question to Q and get the response"
    )
    parser.add_argument("question", nargs="*", help="The question to send to Q")
    parser.add_argument("--file", "-f", help="Read question from file")
    parser.add_argument(
        "--api-key",
        "-k",
        help="API key for the selected provider (defaults to config file or environment variable)",
    )
    parser.add_argument(
        "--model",
        "-m",
        help="Model to use (defaults to config file or model appropriate for the selected provider)",
    )
    parser.add_argument(
        "--provider",
        choices=["anthropic", "vertexai", "groq", "openai"],
        help="LLM provider to use (defaults to config variable DEFAULT_PROVIDER)",
    )
    # Use a mutually exclusive group for interactive mode options
    interactive_group = parser.add_mutually_exclusive_group()
    interactive_group.add_argument(
        "--no-interactive", "-i", action="store_true", help="Disable interactive mode"
    )
    interactive_group.add_argument(
        "--interactive",
        action="store_true",
        help="Force interactive mode without a question",
    )
    parser.add_argument(
        "--no-context",
        "-c",
        action="store_true",
        help="Disable using context from config file",
    )
    parser.add_argument(
        "--no-md",
        "-p",
        action="store_true",
        help="Disable markdown formatting of responses",
    )
    parser.add_argument(
        "--context-file",
        "-x",
        action="append",
        help="Additional file to use as context (can be used multiple times)",
    )
    parser.add_argument(
        "--confirm-context",
        "-w",
        action="store_true",
        help="Show context and ask for confirmation before sending to Q",
    )
    parser.add_argument(
        "--no-empty",
        "-e",
        action="store_true",
        help="Disable sending empty inputs in interactive mode",
    )
    parser.add_argument(
        "--no-execute",
        action="store_true",
        help="Disable command execution functionality",
    )
    parser.add_argument(
        "--no-web",
        action="store_true",
        help="Disable web content fetching functionality",
    )
    parser.add_argument(
        "--no-file-write",
        action="store_true",
        help="Disable file writing functionality",
    )
    parser.add_argument(
        "--file-tree",
        action="store_true",
        help="Include file tree of current directory in context",
    )
    parser.add_argument(
        "--max-context-tokens",
        type=int,
        help="Maximum tokens for context (default: 200000)",
    )
    parser.add_argument(
        "--context-priority-mode",
        choices=["balanced", "code", "conversation"],
        help="Context priority mode (balanced, code, conversation)",
    )
    parser.add_argument(
        "--context-stats",
        action="store_true",
        help="Show context statistics before sending to model",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show program version and exit",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update q to the latest version and exit",
    )
    parser.add_argument(
        "--recover",
        action="store_true",
        help="Recover conversation from the most recent session",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the full message that would be sent to the LLM and exit",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Automatically approve all file operations (WARNING: use only for new projects with nothing to override)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with additional diagnostic output",
    )
    return parser
