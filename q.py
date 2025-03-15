#!/usr/bin/env python3
import argparse
import os
import sys
import anthropic
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.formatted_text import ANSI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.theme import Theme

# Custom theme for the console
custom_theme = Theme({
    "info": "dim cyan",
    "warning": "magenta",
    "error": "bold red",
    "prompt": "orange1",
})

# Initialize Rich console
console = Console(theme=custom_theme)

def read_config_file():
    """Read the configuration file ~/.config/q.conf for API key and context"""
    config_path = os.path.expanduser("~/.config/q.conf")
    api_key = None
    config_vars = {}
    context = ""
    context_started = False
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
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
                        if ('sk-ant' in line.lower() or 'api_key' in line.lower() or 
                            'apikey' in line.lower() or 'key' in line.lower()):
                            line = "[REDACTED - Potential API key or sensitive information]"
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
                            if line.startswith('sk-ant'):  # Even stricter validation
                                api_key = line
        except Exception as e:
            console.print(f"Warning: Error reading config file: {e}", style="warning")
    
    return api_key, context.strip(), config_vars

def format_markdown(text):
    """Format markdown text into Rich-formatted text for terminal display"""
    return Markdown(text)

def get_input_with_escape(prompt="", history=None):
    """Get user input with support for escape key to exit and history navigation"""
    
    # Initialize history
    if history is None:
        history = []
    
    # Create key bindings with escape key handling
    kb = KeyBindings()
    
    # We need to raise an exception instead of calling sys.exit() directly
    class EscapePressed(Exception):
        """Exception raised when escape key is pressed."""
        pass
    
    @kb.add(Keys.Escape)
    def _(event):
        """Exit on escape key press"""
        event.app.exit(exception=EscapePressed())
    
    # Convert Rich markup to ANSI for prompt_toolkit
    # This creates a prompt that looks similar to the Rich one
    ansi_prompt = f"\033[38;5;214m{prompt.replace('[prompt]', '').replace('[/prompt]', '')}\033[0m"
    
    try:
        # Create a prompt session with history
        session = PromptSession(
            history=InMemoryHistory(), 
            key_bindings=kb,
            enable_history_search=True
        )
        
        # Add history items
        for item in history:
            session.history.append_string(item)
        
        # Get input
        try:
            line = session.prompt(ANSI(ansi_prompt))
        except EscapePressed:
            # Handle escape key press
            sys.exit(0)
        
        # Check for "exit" or "quit" commands
        if line.strip().lower() in ["exit", "quit"]:
            sys.exit(0)
            
        return line
        
    except KeyboardInterrupt:
        # Handle Ctrl+C
        print()
        sys.exit(0)
        
    except EOFError:
        # Handle Ctrl+D
        print()
        sys.exit(0)
        
    except Exception as e:
        # Fall back to simple input if prompt_toolkit has issues
        if os.environ.get("Q_DEBUG"):
            console.print(f"Warning: Input error: {e}", style="warning")
        # Try with standard input as a last resort
        try:
            line = input("\033[38;5;214m-> \033[0m")
            if line.strip().lower() in ["exit", "quit"]:
                sys.exit(0)
            return line
        except (KeyboardInterrupt, EOFError):
            print()
            sys.exit(0)

def read_context_file(file_path):
    """Read a context file and return its contents, ensuring no API keys are included"""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
            # Filter out potential API keys (simple pattern matching)
            filtered_lines = []
            for line in content.split('\n'):
                # Skip lines that look like API keys
                if ('sk-ant' in line.lower() or 'api_key' in line.lower() or 
                    'apikey' in line.lower() or 'key' in line.lower()):
                    filtered_lines.append("[REDACTED - Potential API key or sensitive information]")
                else:
                    filtered_lines.append(line)
            return '\n'.join(filtered_lines)
    except Exception as e:
        console.print(f"Warning: Error reading context file {file_path}: {e}", style="warning")
        return ""

def main():
    parser = argparse.ArgumentParser(description="Send a question to Claude and get the response")
    parser.add_argument("question", nargs="*", help="The question to send to Claude")
    parser.add_argument("--file", "-f", help="Read question from file")
    parser.add_argument("--api-key", help="Anthropic API key (defaults to config file or ANTHROPIC_API_KEY env var)")
    parser.add_argument("--model", help="Model to use (defaults to config file or claude-3-opus-20240229)")
    parser.add_argument("--no-interactive", action="store_true", help="Disable interactive mode")
    parser.add_argument("--no-context", action="store_true", help="Disable using context from config file")
    parser.add_argument("--no-md", action="store_true", help="Disable markdown formatting of responses")
    parser.add_argument("--context-file", action="append", help="Additional file to use as context (can be used multiple times)")
    
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
        args.model = config_vars.get("MODEL", "claude-3-opus-20240229")
    
    if not api_key:
        console.print("Error: Anthropic API key not provided. Add to ~/.config/q.conf, set ANTHROPIC_API_KEY environment variable, or use --api-key", style="error")
        sys.exit(1)

    # Initialize client
    client = anthropic.Anthropic(api_key=api_key)
    
    # Initialize conversation history and input history
    conversation = []
    input_history = []
    
    # Build context from config file and context files
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
    
    # Set up system prompt with context if available
    system_prompt = "You are a helpful AI assistant. Provide accurate, concise answers."
    if context:
        # Print debug info about context if verbose
        if os.environ.get("Q_DEBUG"):
            console.print(f"[info]Context from config: {bool(config_context)}[/info]")
            console.print(f"[info]Context files: {args.context_file or []}[/info]")
            console.print(f"[info]Combined context length: {len(context.strip())} characters[/info]")
        
        # Final security check for API keys in combined context
        sanitized_context = context.strip()
        for pattern in ['sk-ant', 'api_key', 'apikey', 'token', 'secret']:
            if pattern in sanitized_context.lower():
                console.print(f"Warning: Potentially sensitive information matching '{pattern}' found in context. Redacting.", style="warning")
                lines = sanitized_context.split('\n')
                for i, line in enumerate(lines):
                    if pattern in line.lower():
                        lines[i] = "[REDACTED - Potential sensitive information]"
                sanitized_context = '\n'.join(lines)
        
        system_prompt += "\n\nHere is some context that may be helpful:\n" + sanitized_context
    
    # Get initial question from args or file
    if args.file:
        try:
            with open(args.file, 'r') as f:
                question = f.read()
        except Exception as e:
            console.print(f"Error reading file: {e}", style="error")
            sys.exit(1)
    elif args.question:
        question = " ".join(args.question)
    elif not args.no_interactive:
        # If no question but interactive mode, prompt for first question
        try:
            # Use custom input function with escape key support
            question = get_input_with_escape("[prompt]-> [/prompt]", input_history)
            # Check for exit command
            if question.strip().lower() in ["exit", "quit"]:
                sys.exit(0)
        except (KeyboardInterrupt, EOFError):
            sys.exit(0)
    else:
        console.print("Error: No question provided. Use positional arguments or --file", style="error")
        sys.exit(1)
    
    # Process questions (initial and then interactive if enabled)
    try:
        while question:
            # Check for exit command before processing
            if question.strip().lower() in ["exit", "quit"]:
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
                        max_tokens=4096,
                        temperature=0,
                        system=system_prompt,
                        messages=conversation
                    )
                
                # Get response
                response = message.content[0].text
                
                # Print formatted response
                if not args.no_md:
                    console.print(Panel(format_markdown(response), border_style="dim"))
                else:
                    console.print(response)
                
                # Add assistant response to conversation history
                conversation.append({"role": "assistant", "content": response})
                
                # If not in interactive mode, exit after first response
                if args.no_interactive:
                    break
                    
                # Get next question
                try:
                    # Use custom input function with escape key support
                    question = get_input_with_escape("[prompt]-> [/prompt]", input_history)
                except (KeyboardInterrupt, EOFError):
                    sys.exit(0)
                
            except Exception as e:
                console.print(f"Error communicating with Claude: {e}", style="error")
                sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        # Handle Ctrl+C or Ctrl+D gracefully
        sys.exit(0)

if __name__ == "__main__":
    main()