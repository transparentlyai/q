#!/usr/bin/env python3
"""
Q - A quick command-line interface for Claude AI.
This module provides a simple CLI for interacting with Claude AI,
with support for conversation history, markdown formatting, and more.
"""
import argparse
import os
import sys
from typing import Dict, List, Optional, Tuple, Any

# Third-party imports
import anthropic
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.markdown import Markdown
from rich.theme import Theme

__version__ = "0.3.4"

# Constants
DEFAULT_MODEL = "claude-3.7-latest"
DEFAULT_MAX_TOKENS = 4096
CONFIG_PATH = os.path.expanduser("~/.config/q.conf")
HISTORY_PATH = os.path.expanduser("~/.qhistory")
SENSITIVE_PATTERNS = ['sk-ant', 'api_key', 'apikey', 'token', 'secret', 'key']
REDACTED_TEXT = "[REDACTED - Potential sensitive information]"
EXIT_COMMANDS = ["exit", "quit"]

# Custom theme for the console
custom_theme = Theme({
    "info": "dim cyan",
    "warning": "magenta",
    "error": "bold red",
    "prompt": "orange1",
})

# Initialize Rich console
console = Console(theme=custom_theme)

def contains_sensitive_info(text: str) -> bool:
    """Check if text contains potentially sensitive information."""
    text_lower = text.lower()
    return any(pattern in text_lower for pattern in SENSITIVE_PATTERNS)

def read_config_file() -> Tuple[Optional[str], str, Dict[str, str]]:
    """
    Read the configuration file for API key and context.
    
    Returns:
        Tuple containing:
        - API key (or None if not found)
        - Context string
        - Dictionary of configuration variables
    """
    api_key = None
    config_vars = {}
    context = ""
    context_started = False
    
    # Create example config path for reference
    example_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "example_config.conf")
    
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                for line in f:
                    line = line.strip()
                    
                    # Check for context section marker
                    if line == "#CONTEXT":
                        context_started = True
                        continue
                        
                    # Skip comments (but not in context section)
                    if line.startswith('#') and not context_started:
                        continue
                    
                    if context_started:
                        # Filter out potential API keys in context
                        if contains_sensitive_info(line):
                            line = REDACTED_TEXT
                        context += line + "\n"
                    else:
                        # Parse configuration variables (KEY=value format)
                        if '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip().upper()
                            value = value.strip()
                            
                            # Store in config vars
                            config_vars[key] = value
                            
                            # Check for API key specifically
                            if key == "ANTHROPIC_API_KEY" and not api_key:
                                api_key = value
                        # Check for API key (assuming it's just the key on a line by itself)
                        elif not api_key and len(line) > 20:  # Simple validation for API key-like string
                            if line.startswith('sk-ant-api'):  # Strict validation for v1 API key format
                                api_key = line
        except Exception as e:
            console.print(f"Warning: Error reading config file: {e}", style="warning")
    else:
        # If config file doesn't exist, suggest creating it using the example format
        if os.path.exists(example_config_path):
            console.print(f"Config file not found. You can create one at {CONFIG_PATH} using the format shown in {example_config_path}", style="info")
            console.print("Make sure your API key starts with 'sk-ant-api' for Claude API v1 format.", style="info")
    
    return api_key, context.strip(), config_vars

def format_markdown(text: str) -> Markdown:
    """
    Format markdown text into Rich-formatted text for terminal display.
    
    Args:
        text: The markdown text to format
        
    Returns:
        A Rich Markdown object that can be printed to the console
    """
    return Markdown(text)

def get_input(prompt: str = "", session: Optional[PromptSession] = None) -> str:
    """
    Get user input using prompt_toolkit with history support.
    
    Args:
        prompt: The prompt text to display
        session: Optional PromptSession object for history and styling
        
    Returns:
        The input text provided by the user
        
    Raises:
        SystemExit: If the user exits with Ctrl+C, Ctrl+D, or by typing exit/quit
    """
    try:
        # Use the provided session or create a default one
        if session:
            # Create HTML-formatted prompt for prompt_toolkit
            formatted_prompt = HTML(f'<prompt>{prompt}</prompt>')
            
            # Use prompt_toolkit with proper formatting
            line = session.prompt(
                formatted_prompt,
                enable_history_search=True  # Enable history navigation (up/down arrows)
            )
        else:
            # Fallback to input if no session (shouldn't happen)
            line = input(prompt)
        
        # Check for exit commands
        if line.strip().lower() in EXIT_COMMANDS:
            sys.exit(0)
            
        return line
        
    except (KeyboardInterrupt, EOFError):
        # Handle Ctrl+C or Ctrl+D
        print()
        sys.exit(0)

def read_context_file(file_path: str) -> str:
    """
    Read a context file and return its contents, ensuring no API keys are included.
    
    Args:
        file_path: Path to the context file to read
        
    Returns:
        The sanitized content of the file as a string
    """
    try:
        with open(file_path, 'r') as f:
            content = f.read()
            # Filter out potential API keys (simple pattern matching)
            filtered_lines = []
            for line in content.split('\n'):
                # Skip lines that look like API keys
                if contains_sensitive_info(line):
                    filtered_lines.append(REDACTED_TEXT)
                else:
                    filtered_lines.append(line)
            return '\n'.join(filtered_lines)
    except Exception as e:
        console.print(f"Warning: Error reading context file {file_path}: {e}", style="warning")
        return ""

def setup_argparse() -> argparse.ArgumentParser:
    """Set up the argument parser for the CLI."""
    parser = argparse.ArgumentParser(description="Send a question to Claude and get the response")
    parser.add_argument("question", nargs="*", help="The question to send to Claude")
    parser.add_argument("--file", "-f", help="Read question from file")
    parser.add_argument("--api-key", "-k", help="Anthropic API key (defaults to config file or ANTHROPIC_API_KEY env var)")
    parser.add_argument("--model", "-m", help="Model to use (defaults to config file or claude-3-opus-20240229)")
    parser.add_argument("--no-interactive", "-i", action="store_true", help="Disable interactive mode")
    parser.add_argument("--no-context", "-c", action="store_true", help="Disable using context from config file")
    parser.add_argument("--no-md", "-p", action="store_true", help="Disable markdown formatting of responses")
    parser.add_argument("--context-file", "-x", action="append", help="Additional file to use as context (can be used multiple times)")
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}", help="Show program version and exit")
    return parser

def create_prompt_session() -> PromptSession:
    """Create and configure a PromptSession for input handling."""
    # Define prompt style with orange color
    prompt_style = Style.from_dict({
        'prompt': '#ff8800 bold',  # Orange and bold
    })
    
    # Create history object
    history = FileHistory(HISTORY_PATH)
    
    # Create prompt session with history and style
    prompt_session = PromptSession(
        history=history,
        style=prompt_style,
        vi_mode=False,    # Use standard emacs-like keybindings
        complete_in_thread=True,  # More responsive completion
        mouse_support=False  # Disable mouse support to allow normal terminal scrolling
    )
    
    if os.environ.get("Q_DEBUG"):
        console.print(f"[info]Using history file: {HISTORY_PATH}[/info]")
        
    return prompt_session

def build_context(args: argparse.Namespace, config_context: str) -> str:
    """
    Build the context from config and additional context files.
    
    Args:
        args: Command line arguments
        config_context: Context from the config file
        
    Returns:
        Combined context string
    """
    context = ""
    
    # Add config context if not disabled
    if config_context and not args.no_context:
        context += config_context + "\n\n"
    
    # Add context from additional files
    if args.context_file:
        for file_path in args.context_file:
            file_content = read_context_file(file_path)
            if file_content:
                context += f"Content from {os.path.basename(file_path)}:\n{file_content}\n\n"
    
    context = context.strip()
    
    # Debug output
    if context and os.environ.get("Q_DEBUG"):
        console.print(f"[info]Context from config: {bool(config_context)}[/info]")
        console.print(f"[info]Context files: {args.context_file or []}[/info]")
        console.print(f"[info]Combined context length: {len(context)} characters[/info]")
    
    return context

def sanitize_context(context: str) -> str:
    """Ensure no sensitive information is present in the context."""
    if not context:
        return ""
        
    lines = context.split('\n')
    for i, line in enumerate(lines):
        if contains_sensitive_info(line):
            console.print(f"Warning: Potentially sensitive information found in context. Redacting.", style="warning")
            lines[i] = REDACTED_TEXT
    
    return '\n'.join(lines)

def get_initial_question(args: argparse.Namespace, prompt_session: PromptSession, history: FileHistory) -> str:
    """
    Get the initial question from command line, file, or prompt.
    
    Returns:
        The initial question string
    """
    if args.file:
        try:
            with open(args.file, 'r') as f:
                question = f.read()
            # Add file content to history
            history.append_string(question.strip())
            return question
        except Exception as e:
            console.print(f"Error reading file: {e}", style="error")
            sys.exit(1)
    elif args.question:
        question = " ".join(args.question)
        # Add command-line question to history
        history.append_string(question.strip())
        return question
    elif not args.no_interactive:
        # If no question but interactive mode, prompt for first question
        return get_input("> ", session=prompt_session)
    else:
        console.print("Error: No question provided. Use positional arguments or --file", style="error")
        sys.exit(1)

def handle_claude_error(e: Exception) -> None:
    """Handle errors from the Claude API in a consistent way."""
    if isinstance(e, anthropic.APIStatusError):
        if e.status_code == 401:
            console.print("Authentication error: Your API key appears to be invalid. Please check your API key.", style="error")
        else:
            console.print(f"Error communicating with Claude (Status {e.status_code}): {e.message}", style="error")
    elif isinstance(e, anthropic.APIConnectionError):
        console.print(f"Connection error: Could not connect to Anthropic API. Please check your internet connection.", style="error")
    elif isinstance(e, anthropic.APITimeoutError):
        console.print(f"Timeout error: The request to Anthropic API timed out.", style="error")
    else:
        console.print(f"Error communicating with Claude: {e}", style="error")
        
    if os.environ.get("Q_DEBUG"):
        console.print(f"Error details: {e}", style="error")
    
    sys.exit(1)

def main() -> None:
    """Main entry point for the CLI."""
    parser = setup_argparse()
    
    # If no args provided (sys.argv has just the script name), print help and exit
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
        
    args = parser.parse_args()

    # Get API key and config vars from config file
    config_api_key, config_context, config_vars = read_config_file()
    
    # Use API key from args, config file, or environment variable (in that order)
    api_key = args.api_key or config_api_key or os.environ.get("ANTHROPIC_API_KEY")
    
    # Set model from args, config file, or default
    if not args.model:
        args.model = config_vars.get("MODEL", DEFAULT_MODEL)
        
    # Set max_tokens from config file or default
    max_tokens = int(config_vars.get("MAX_TOKENS", DEFAULT_MAX_TOKENS))
    
    if not api_key:
        console.print("Error: Anthropic API key not provided. Add to ~/.config/q.conf, set ANTHROPIC_API_KEY environment variable, or use --api-key", style="error")
        sys.exit(1)

    # Initialize client
    client = anthropic.Anthropic(api_key=api_key)
    
    # Initialize conversation history and input history
    conversation = []
    input_history = []
    
    # Set up prompt session for input
    prompt_session = create_prompt_session()
    history = prompt_session.history
    
    # Build and sanitize context from config and files
    context = build_context(args, config_context)
    sanitized_context = sanitize_context(context)
    
    # Set up system prompt with context if available
    system_prompt = "You are a helpful AI assistant. Provide accurate, concise answers."
    if sanitized_context:
        system_prompt += "\n\nHere is some context that may be helpful:\n" + sanitized_context
    
    # Get initial question from args, file, or prompt
    try:
        question = get_initial_question(args, prompt_session, history)
    except (KeyboardInterrupt, EOFError):
        sys.exit(0)
    
    # Process questions (initial and then interactive if enabled)
    try:
        while question:
            # Check for exit command before processing
            if question.strip().lower() in EXIT_COMMANDS:
                sys.exit(0)
                
            # Add user message to conversation and input history
            conversation.append({"role": "user", "content": question})
            
            # Only add non-empty questions that aren't duplicates of the last entry
            if question.strip() and (not input_history or question != input_history[-1]):
                input_history.append(question.strip())
            
            # Send question to Claude
            try:
                with console.status("[info]Thinking...[/info]"):
                    message = client.messages.create(
                        model=args.model,
                        max_tokens=max_tokens,
                        temperature=0,
                        system=system_prompt,
                        messages=conversation
                    )
                
                # Get response
                response = message.content[0].text
                
                # Print formatted response
                console.print("")  # Add empty line before response
                if not args.no_md:
                    console.print(format_markdown(response))
                else:
                    console.print(response)
                console.print("")  # Add empty line after response
                
                # Add assistant response to conversation history
                conversation.append({"role": "assistant", "content": response})
                
                # If not in interactive mode, exit after first response
                if args.no_interactive:
                    break
                    
                # Get next question
                question = get_input("> ", session=prompt_session)
                
            except Exception as e:
                handle_claude_error(e)
                
    except (KeyboardInterrupt, EOFError):
        # Handle Ctrl+C or Ctrl+D gracefully
        pass
    finally:
        # prompt_toolkit's FileHistory automatically saves history
        if os.environ.get("Q_DEBUG"):
            console.print(f"[info]History saved to {HISTORY_PATH}[/info]")
        sys.exit(0)

# Type definitions for better code clarity
Message = Dict[str, str]
Conversation = List[Message]

if __name__ == "__main__":
    main()