"""Input handling for q_cli."""

import os
import sys
import signal
from typing import Optional
import re

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.completion import PathCompleter, Completer, Completion
from prompt_toolkit.document import Document
from rich.console import Console

from q_cli.utils.constants import HISTORY_PATH, EXIT_COMMANDS
from q_cli.utils.helpers import format_markdown

# No need for global events - we'll use prompt_toolkit's native abort mechanism


class InlinePathCompleter(Completer):
    """Custom completer that enables file path completion anywhere in the text.
    
    This completer will locate partial file paths in the current input text
    and provide completions, rather than just working at the beginning of the text.
    """
    
    def __init__(self, expanduser=True, only_directories=False, min_input_len=1):
        """Initialize the completer.
        
        Args:
            expanduser: Expand ~ in paths to the user's home directory
            only_directories: Only complete directories, not files
            min_input_len: Minimum length of text before completion is attempted
        """
        self.expanduser = expanduser
        self.only_directories = only_directories
        self.min_input_len = min_input_len
        # Use built-in PathCompleter for the actual path completion
        self.path_completer = PathCompleter(
            expanduser=expanduser,
            only_directories=only_directories
        )
    
    def get_completions(self, document, complete_event):
        """Get completions for the current document.
        
        This method analyzes the text to find potential file paths to complete.
        It looks for partial file paths and provides completions for them.
        """
        # Get cursor position and text
        cursor_pos = document.cursor_position
        text = document.text[:cursor_pos]
        
        if not text or len(text) < self.min_input_len:
            return
            
        # Find the partial path closest to the cursor
        # This regex matches partial paths, including those starting with ~, ./, or /
        partial_path_match = re.search(r'(^|[\s=\'"])(~{1}|\.{1,2})?[/\\]?([^\'"\s]*)$', text)
        
        if partial_path_match:
            # Get the start position of the match and the partial path
            partial_path_start = partial_path_match.start(3)
            path_prefix = partial_path_match.group(2) or ''
            partial_path = partial_path_match.group(3) or ''
            
            # Create a new document with just the path for the path completer
            path_document = Document(
                text=f"{path_prefix}{partial_path}", 
                cursor_position=len(f"{path_prefix}{partial_path}")
            )
            
            # Get completions from the path completer
            for completion in self.path_completer.get_completions(path_document, complete_event):
                # Calculate display offset from current cursor position
                display_meta = completion.display_meta if completion.display_meta else ""
                
                # Adjust the position of the completion
                yield Completion(
                    completion.text,
                    start_position=partial_path_start - cursor_pos,
                    display_meta=display_meta,
                    display=completion.display,
                    style=completion.style
                )


def create_prompt_session(console: Console) -> PromptSession:
    """Create and configure a PromptSession with file path completion."""
    # Define prompt style with orange color
    prompt_style = Style.from_dict(
        {
            "prompt": "#ff8800 bold",  # Orange and bold
            "completion": "bg:#444444 #ffffff",  # Gray background for completion menu
            "completion.current": "bg:#008888 #ffffff",  # Highlight selected completion
        }
    )

    # Create history object
    history = FileHistory(HISTORY_PATH)
    
    # Create custom keybindings
    bindings = create_key_bindings()
    
    # Create inline path completer for file autocompletion anywhere in the input
    inline_completer = InlinePathCompleter(
        expanduser=True,  # Expand ~ to home directory
        min_input_len=1,  # Start completing after at least 1 character
        only_directories=False,  # Complete both files and directories
    )

    # Create prompt session with history, style, and path completion
    prompt_session: PromptSession = PromptSession(
        history=history,
        style=prompt_style,
        key_bindings=bindings,
        vi_mode=False,  # Use standard emacs-like keybindings
        complete_in_thread=True,  # More responsive completion
        mouse_support=False,  # Disable mouse support to allow normal terminal scrolling
        completer=inline_completer,  # Enable inline file path completion
    )

    if os.environ.get("Q_DEBUG"):
        console.print(f"[info]Using history file: {HISTORY_PATH}[/info]")

    return prompt_session


def create_key_bindings():
    """Create custom key bindings for the prompt session."""
    bindings = KeyBindings()
    
    # Create a separate key binding for ESC to exit immediately
    escape_bindings = KeyBindings()
    
    # Override the Enter key to only accept input when there's text
    @bindings.add("enter")
    def handle_enter(event):
        """Submit text when Enter is pressed and there's text."""
        # Only accept input if there's text
        if len(event.current_buffer.text.strip()) > 0:
            event.current_buffer.validate_and_handle()
    
    # Add Escape key to abort/exit with highest priority
    @escape_bindings.add("escape", eager=True)
    def handle_escape(event):
        """Exit the application when Escape is pressed."""
        # Send SIGINT to the current process, which is a cleaner way to exit
        os.kill(os.getpid(), signal.SIGINT)
    
    # Merge the key bindings, with escape_bindings having higher precedence
    return merge_key_bindings([escape_bindings, bindings])


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
            formatted_prompt = HTML(f"<prompt>{prompt}</prompt>")

            # Use prompt_toolkit with proper formatting and completion
            line = session.prompt(
                formatted_prompt,
                enable_history_search=True,  # Enable history navigation (up/down arrows)
                complete_while_typing=True,  # Show completions while typing
            )
        else:
            # Fallback to input if no session (shouldn't happen)
            line = input(prompt)

        # Check for exit commands
        if line.strip().lower() in EXIT_COMMANDS:
            sys.exit(0)

        return line

    except KeyboardInterrupt:
        # Handle Ctrl+C or ESC key (which we mapped to KeyboardInterrupt)
        sys.exit(0)
    except EOFError:
        # Handle Ctrl+D
        sys.exit(0)


def get_initial_question(
    args, prompt_session: PromptSession, history
) -> str:
    """
    Get the initial question from command line, file, or prompt.

    Returns:
        The initial question string
    """
    # If interactive mode is explicitly forced, go straight to prompt
    if getattr(args, "interactive", False):
        # If interactive mode is forced, prompt for first question
        while True:
            question = get_input("Q> ", session=prompt_session)
            # If input is not empty or --no-empty flag is not set, proceed
            if not args.no_empty or question.strip():
                return question
    elif args.file:
        try:
            with open(args.file, "r") as f:
                question = f.read()
            # Add file content to history
            history.append_string(question.strip())
            return question
        except Exception as e:
            from rich.console import Console

            Console().print(f"Error reading file: {e}", style="error")
            sys.exit(1)
    elif args.question:
        question = " ".join(args.question)
        # Add command-line question to history
        history.append_string(question.strip())
        return question
    elif not args.no_interactive:
        # If no question but interactive mode, prompt for first question (handling empty inputs)
        while True:
            question = get_input("Q> ", session=prompt_session)
            # If input is not empty or --no-empty flag is not set, proceed
            if not args.no_empty or question.strip():
                return question
    else:
        from rich.console import Console

        Console().print(
            "Error: No question provided. Use positional arguments or --file",
            style="error",
        )
        sys.exit(1)


def confirm_context(
    prompt_session: PromptSession, system_prompt: str, console: Console
) -> bool:
    """Show the context and ask for user confirmation."""
    console.print("\n[bold]System prompt that will be sent to Q:[/bold]")
    console.print(format_markdown(system_prompt))
    console.print("")

    while True:
        response = (
            get_input("Send this context to Q? [Y/n] ", session=prompt_session)
            .strip()
            .lower()
        )
        if response == "" or response.startswith("y"):
            return True
        elif response.startswith("n"):
            return False
        else:
            console.print("Please answer Y or N", style="warning")