"""Input handling for q_cli."""

import os
import sys
import signal
from typing import Optional, List, Tuple
import re
import glob

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.completion import Completer, Completion, PathCompleter, NestedCompleter
from prompt_toolkit.document import Document
from rich.console import Console

from q_cli.utils.constants import (
    HISTORY_PATH, 
    EXIT_COMMANDS, 
    get_debug, 
    SAVE_COMMAND_PREFIX,
    RECOVER_COMMAND,
    TRANSPLANT_COMMAND
)
from q_cli.utils.helpers import format_markdown


class SlashCommandCompleter(Completer):
    """
    Completer for slash commands.
    """
    
    def __init__(self):
        """Initialize the slash command completer."""
        # Map commands to their help descriptions
        self.commands = {
            SAVE_COMMAND_PREFIX: "Save the last response to a file",
            RECOVER_COMMAND: "Recover a previous session",
            TRANSPLANT_COMMAND: "Change the active provider and model"
        }
    
    def get_completions(self, document, complete_event):
        """
        Get completions for the current document.
        
        Args:
            document: The current document being edited
            complete_event: The completion event
            
        Yields:
            Completion objects
        """
        # Only provide completions at the start of the line
        if not document.text.startswith('/'):
            return
            
        # Get the text up to the cursor
        text = document.text_before_cursor
        
        # Find completions for the current text
        for command, description in self.commands.items():
            if command.startswith(text):
                # Return the remaining part of the command
                yield Completion(
                    command[len(text):],
                    start_position=0,
                    display=command,
                    display_meta=description
                )


class CombinedCompleter(Completer):
    """
    Completer that combines slash command completion and path completion.
    """
    
    def __init__(self):
        """Initialize the combined completer."""
        self.slash_completer = SlashCommandCompleter()
        self.path_completer = SmartPathCompleter()
    
    def get_completions(self, document, complete_event):
        """
        Get completions from either slash commands or paths depending on context.
        
        Args:
            document: The current document being edited
            complete_event: The completion event
            
        Yields:
            Completion objects
        """
        text = document.text_before_cursor
        
        # Special case for /save command - provide path completion
        if text.startswith(f"{SAVE_COMMAND_PREFIX} "):
            # Get the part after "/save "
            path_text = text[len(SAVE_COMMAND_PREFIX) + 1:]
            # Create a new document with just the path part
            path_document = Document(path_text, cursor_position=len(path_text))
            # Use path completer for this part
            for completion in self.path_completer.get_completions(path_document, complete_event):
                # Adjust the start position to account for "/save " prefix
                completion.start_position -= len(path_text)
                
                # If the completion is for a directory, add "Directory" in the display meta
                if completion.display_meta == "Directory":
                    completion.display_meta = "Save to this directory"
                # For files, add a more descriptive message
                else:
                    completion.display_meta = "Save to this file"
                
                yield completion
        # If the input starts with a slash but is not complete yet, use slash command completer
        elif text.startswith('/'):
            for completion in self.slash_completer.get_completions(document, complete_event):
                yield completion
        # For all other text, use the smart path completer
        else:
            for completion in self.path_completer.get_completions(document, complete_event):
                yield completion


class SmartPathCompleter(Completer):
    """
    Path completer that works anywhere in the input text.

    This completer scans the text at the current cursor position to find any
    partial path or filename, then offers completions for it.
    """

    def __init__(self):
        """Initialize the smart path completer."""
        # Built-in path completer for comparison
        self.path_completer = PathCompleter(expanduser=True)

    def get_word_under_cursor(self, document: Document) -> Tuple[str, int]:
        """
        Get the word under cursor and its start position.

        Args:
            document: The document being edited

        Returns:
            Tuple containing (word, start_position)
        """
        # Get text up to cursor
        text_before_cursor = document.text_before_cursor

        # Find potential path fragments that could be completed
        # Look for words that might be files or directories
        # This simpler regex finds anything that doesn't contain whitespace
        match = re.search(r"[^\s]*$", text_before_cursor)

        if match:
            word = match.group(0)
            start_pos = len(text_before_cursor) - len(word)
            return word, start_pos

        return "", document.cursor_position

    def get_path_completions(self, current_word: str) -> List[Tuple[str, str]]:
        """
        Get possible path completions for the current word.

        Args:
            current_word: The word to complete

        Returns:
            List of (completion, display_meta) tuples
        """
        # Handle empty input
        if not current_word:
            matches = []
            for f in os.listdir("."):
                # Skip hidden files
                if f.startswith("."):
                    continue
                    
                if os.path.isdir(f):
                    # Add trailing slash for directories
                    matches.append((f"{f}/", "Directory"))
                else:
                    # Determine file type based on extension
                    ext = os.path.splitext(f)[1].lower()
                    if ext in ['.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.c', '.cpp', '.go', '.rs']:
                        display_meta = "Source code"
                    elif ext in ['.md', '.txt', '.rst', '.adoc']:
                        display_meta = "Text file"
                    elif ext in ['.json', '.yaml', '.yml', '.toml', '.ini', '.conf']:
                        display_meta = "Config file"
                    elif ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp']:
                        display_meta = "Image"
                    elif ext in ['.pdf', '.docx', '.xlsx', '.pptx']:
                        display_meta = "Document"
                    else:
                        display_meta = "File"
                    matches.append((f, display_meta))
            return matches

        # Check if it's a path with directory components
        if "/" in current_word:
            # Get the directory part and the filename part
            directory, filename = os.path.split(current_word)

            # Handle special case for current directory
            if directory == "":
                directory = "."

            # Expand user home if needed
            if directory.startswith("~"):
                directory = os.path.expanduser(directory)

            try:
                # Get all matching files in that directory
                if os.path.isdir(directory):
                    matches = []
                    pattern = (
                        f"{directory}/{filename}*" if filename else f"{directory}/*"
                    )
                    for path in glob.glob(pattern):
                        # Get just the relevant part for completion
                        name = os.path.basename(path)
                        if os.path.isdir(path):
                            # Add trailing slash for directories
                            display_meta = "Directory"
                            completion = f"{os.path.join(directory, name)}/"
                        else:
                            # Determine file type based on extension
                            ext = os.path.splitext(name)[1].lower()
                            if ext in ['.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.c', '.cpp', '.go', '.rs']:
                                display_meta = "Source code"
                            elif ext in ['.md', '.txt', '.rst', '.adoc']:
                                display_meta = "Text file"
                            elif ext in ['.json', '.yaml', '.yml', '.toml', '.ini', '.conf']:
                                display_meta = "Config file"
                            elif ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp']:
                                display_meta = "Image"
                            elif ext in ['.pdf', '.docx', '.xlsx', '.pptx']:
                                display_meta = "Document"
                            else:
                                display_meta = "File"
                            completion = os.path.join(directory, name)

                        # Only include files that match the prefix
                        if not filename or name.startswith(filename):
                            matches.append((completion, display_meta))
                    return matches
            except (PermissionError, FileNotFoundError):
                return []
        else:
            # Simple filename matching in current directory
            matches = []
            for name in os.listdir("."):
                if name.startswith(current_word):
                    if os.path.isdir(name):
                        # Add trailing slash for directories
                        matches.append((f"{name}/", "Directory"))
                    else:
                        # Determine file type based on extension
                        ext = os.path.splitext(name)[1].lower()
                        if ext in ['.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.c', '.cpp', '.go', '.rs']:
                            display_meta = "Source code"
                        elif ext in ['.md', '.txt', '.rst', '.adoc']:
                            display_meta = "Text file"
                        elif ext in ['.json', '.yaml', '.yml', '.toml', '.ini', '.conf']:
                            display_meta = "Config file"
                        elif ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp']:
                            display_meta = "Image"
                        elif ext in ['.pdf', '.docx', '.xlsx', '.pptx']:
                            display_meta = "Document"
                        else:
                            display_meta = "File"
                        matches.append((name, display_meta))
            return matches

        return []

    def get_completions(self, document, complete_event):
        """
        Get completions for the current document.

        Args:
            document: The current document being edited
            complete_event: The completion event

        Yields:
            Completion objects
        """
        # Get the word under cursor and its position
        word, word_start = self.get_word_under_cursor(document)

        # Get completions for this word
        completions = self.get_path_completions(word)

        # Convert to Completion objects
        for text, display_meta in completions:
            # Calculate the correct start position
            start_position = word_start - document.cursor_position

            yield Completion(
                text, start_position=start_position, display_meta=display_meta
            )


def create_prompt_session(console: Console) -> PromptSession:
    """Create and configure a PromptSession with file path completion."""
    # Define prompt style with orange color
    prompt_style = Style.from_dict(
        {
            "prompt": "#ff8800 bold",  # Orange and bold
            "completion": "bg:#444444 #ffffff",  # Gray background for completion menu
            "completion.current": "bg:#008888 #ffffff",  # Highlight selected completion
            "warning": "#ff9900 italic",  # Warning messages (for multiline hints)
        }
    )

    # Create history object
    history = FileHistory(HISTORY_PATH)

    # Create custom keybindings
    bindings = create_key_bindings()

    # Create combined completer for both slash commands and paths
    combined_completer = CombinedCompleter()

    # Create prompt session with history, style, and our combined completer
    prompt_session: PromptSession = PromptSession(
        history=history,
        style=prompt_style,
        key_bindings=bindings,
        vi_mode=False,  # Use standard emacs-like keybindings
        complete_in_thread=True,  # More responsive completion
        mouse_support=False,  # Disable mouse support to allow normal terminal scrolling
        completer=combined_completer,  # Use our combined completer
    )

    if get_debug():
        console.print(f"[info]Using history file: {HISTORY_PATH}[/info]")

    return prompt_session


def create_key_bindings():
    """Create custom key bindings for the prompt session."""
    bindings = KeyBindings()

    # Create a separate key binding for ESC to exit immediately
    escape_bindings = KeyBindings()

    # Handle Enter key for submission
    @bindings.add("enter")
    def handle_enter(event):
        """Submit text when Enter is pressed and there's text."""
        # Only process if there's text
        if len(event.current_buffer.text.strip()) > 0:
            # For multiline text, show a hint about Alt+Enter when user first presses Enter
            if "\n" in event.current_buffer.text and not hasattr(event.current_buffer, "_alt_enter_hint_shown"):
                # Add attribute to track that we've shown the hint
                event.current_buffer._alt_enter_hint_shown = True
                
                # Show hint using a more compatible method
                from rich.console import Console
                console = Console()
                console.print("\n[yellow italic]Multiline input detected. Press Enter again to send, or Alt+Enter for a new line[/yellow italic]")
                
                # Return without submitting - next Enter will submit
                return
            
            # Process the submission
            event.current_buffer.validate_and_handle()
    
    # Add Alt+Enter for new lines
    @bindings.add("escape", "enter")  # Alt+Enter is sent as escape followed by enter
    def handle_alt_enter(event):
        """Insert a newline when Alt+Enter is pressed."""
        event.current_buffer.insert_text("\n")
    
    # Support Ctrl+J as an alternative for new lines
    @bindings.add("c-j")  # Ctrl+J is a common alternative for newline
    def handle_ctrl_j(event):
        """Insert a newline when Ctrl+J is pressed."""
        event.current_buffer.insert_text("\n")

    # Add double Escape key to abort/exit with high priority
    # Using double escape to avoid conflict with Alt+Enter which starts with escape
    @escape_bindings.add("escape", "escape", eager=True)
    def handle_double_escape(event):
        """Exit the application when Escape is pressed twice."""
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


def get_initial_question(args, prompt_session: PromptSession, history) -> str:
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

            Console().print(f"[red]Error reading file: {e}[/red]")
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
            "[red]Error: No question provided. Use positional arguments or --file[/red]"
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
