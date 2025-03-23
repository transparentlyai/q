"""Command line argument parsing for q_cli."""

import argparse
from q_cli import __version__


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
        help="Anthropic API key (defaults to config file or ANTHROPIC_API_KEY env var)",
    )
    parser.add_argument(
        "--model",
        "-m",
        help="Model to use (defaults to config file or claude-3-opus-20240229)",
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
        "--version",
        "-v",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show program version and exit",
    )
    return parser
