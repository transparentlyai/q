"""Session management for Q conversations."""

import os
import json
import time
import tempfile
import mmap
from typing import Dict, List, Optional, Any, Tuple
from rich.console import Console
# No need to import anthropic - using litellm only
from q_cli.utils.client import LLMClient
from prompt_toolkit import PromptSession

from q_cli.utils.constants import DEBUG, SESSION_PATH
from q_cli.utils.context import ContextManager


class SessionManager:
    """Manages session persistence and recovery for Q conversations."""

    def __init__(self, console: Console):
        """
        Initialize the session manager.

        Args:
            console: Console instance for output
        """
        self.console = console
        self.session_file = SESSION_PATH
        self._ensure_session_dir()

    def _ensure_session_dir(self) -> None:
        """Ensure the session directory exists."""
        session_dir = os.path.dirname(self.session_file)
        if not os.path.exists(session_dir):
            try:
                os.makedirs(session_dir, exist_ok=True)
                if DEBUG:
                    self.console.print(
                        f"[dim]Created session directory: {session_dir}[/dim]"
                    )
            except Exception as e:
                self.console.print(
                    f"[yellow]Warning: Could not create session directory: {e}[/yellow]"
                )

    def save_session(
        self,
        conversation: List[Dict[str, Any]],
        system_prompt: str,
        context_manager: Optional[ContextManager] = None,
    ) -> bool:
        """
        Save the current conversation session to a file.
        Only keeps the most recent MAX_HISTORY_TURNS of conversation history.

        Args:
            conversation: List of conversation messages
            system_prompt: The system prompt used in the conversation
            context_manager: Optional context manager instance

        Returns:
            True if session was saved successfully, False otherwise
        """
        from q_cli.utils.constants import MAX_HISTORY_TURNS

        try:
            # Make a copy of the conversation to avoid modifying the original
            conversation_copy = conversation.copy()

            # Trim conversation to keep only the most recent turns
            if MAX_HISTORY_TURNS > 0 and conversation_copy:
                # Count user messages to determine turns
                user_msg_indexes = [
                    i
                    for i, msg in enumerate(conversation_copy)
                    if msg.get("role") == "user"
                ]

                # If we have more user messages than our max turns limit
                if len(user_msg_indexes) > MAX_HISTORY_TURNS:
                    # Calculate where to start (keep last MAX_HISTORY_TURNS)
                    # We want to keep user messages from this index and forward
                    start_index = user_msg_indexes[-(MAX_HISTORY_TURNS)]

                    # If this is not the first message, we need to make sure we start with a user message
                    if (
                        start_index > 0
                        and conversation_copy[start_index - 1].get("role")
                        == "assistant"
                    ):
                        # Adjust to include the preceding assistant message to maintain conversation flow
                        start_index -= 1

                    # Keep only the most recent messages
                    conversation_copy = conversation_copy[start_index:]

                    if DEBUG:
                        self.console.print(
                            f"[dim]Trimmed conversation history to last {MAX_HISTORY_TURNS} turns "
                            f"({len(conversation_copy)} messages)[/dim]"
                        )

            # Create session data structure
            session_data = {
                "timestamp": time.time(),
                "conversation": conversation_copy,
                "system_prompt": system_prompt,
            }

            # Add context manager state if available
            if context_manager:
                # Get tokens by priority for restoration
                tokens_by_priority = context_manager.get_tokens_by_priority()
                context_data = {
                    "max_tokens": context_manager.max_tokens,
                    "priority_mode": context_manager.priority_mode,
                    "token_allocations": context_manager.token_allocations,
                    "tokens_by_priority": tokens_by_priority,
                }
                session_data["context_data"] = context_data

            # Use atomic write pattern to prevent corruption if interrupted
            # Write to temp file first, then rename
            with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp_file:
                json.dump(session_data, temp_file, indent=2)
                temp_path = temp_file.name

            # Atomic rename
            os.replace(temp_path, self.session_file)

            if DEBUG:
                self.console.print(f"[dim]Session saved to {self.session_file}[/dim]")

            return True

        except Exception as e:
            if DEBUG:
                self.console.print(f"[yellow]Error saving session: {str(e)}[/yellow]")
            return False

    def load_session(
        self, max_turns: int = 5
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str], Optional[Dict]]:
        """
        Load a previously saved conversation session.

        Args:
            max_turns: Maximum number of conversation turns to load (default: 5)
                       A turn consists of a user message and its corresponding assistant response
                       Use 0 to load all available turns

        Returns:
            Tuple containing:
            - List of conversation messages (or None if not found)
            - System prompt (or None if not found)
            - Context data dictionary (or None if not found)
        """
        if not os.path.exists(self.session_file):
            if DEBUG:
                self.console.print(
                    f"[yellow]No session file found at {self.session_file}[/yellow]"
                )
            return None, None, None

        try:
            # Use memory mapping for efficient loading of large files
            with open(self.session_file, "r+") as f:
                # Get file size
                file_size = os.path.getsize(self.session_file)

                if file_size > 0:
                    # For small files, read directly
                    if file_size < 10_000_000:  # 10MB threshold
                        session_data = json.load(f)
                    else:
                        # For large files, use memory mapping
                        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                            session_json = mm.read().decode("utf-8")
                            session_data = json.loads(session_json)

                    conversation = session_data.get("conversation", [])
                    system_prompt = session_data.get("system_prompt", "")
                    context_data = session_data.get("context_data", None)

                    # Apply max_turns limit - keep only the most recent turns
                    # Special case: max_turns = 0 means load all available turns
                    if max_turns > 0 and conversation:
                        # Count user messages to determine turns
                        user_msg_indexes = [
                            i
                            for i, msg in enumerate(conversation)
                            if msg.get("role") == "user"
                        ]

                        # If we have more user messages than our max turns limit
                        if len(user_msg_indexes) > max_turns:
                            # Calculate where to start (keep last max_turns)
                            # We want to keep user messages from this index and forward
                            start_index = user_msg_indexes[-(max_turns)]

                            # If this is not the first message, we need to make sure we start with a user message
                            if (
                                start_index > 0
                                and conversation[start_index - 1].get("role")
                                == "assistant"
                            ):
                                # Adjust to include the preceding assistant message to maintain conversation flow
                                start_index -= 1

                            # Keep only the most recent messages
                            conversation = conversation[start_index:]

                            if DEBUG:
                                self.console.print(
                                    f"[dim]Trimmed conversation history to last {max_turns} turns "
                                    f"({len(conversation)} messages)[/dim]"
                                )

                    if DEBUG:
                        self.console.print(
                            f"[dim]Loaded session from {self.session_file} "
                            f"({len(conversation)} messages)[/dim]"
                        )

                    return conversation, system_prompt, context_data
                else:
                    if DEBUG:
                        self.console.print(f"[yellow]Session file is empty[/yellow]")
                    return None, None, None

        except Exception as e:
            self.console.print(f"[yellow]Error loading session: {str(e)}[/yellow]")

            # If the file is corrupted, try to make a backup
            try:
                backup_file = f"{self.session_file}.bak"
                os.replace(self.session_file, backup_file)
                self.console.print(
                    f"[yellow]Corrupted session file backed up to {backup_file}[/yellow]"
                )
            except Exception:
                pass

            return None, None, None

    def restore_context_manager(
        self, context_data: Dict, console: Console
    ) -> Optional[ContextManager]:
        """
        Restore a context manager from saved context data.

        Args:
            context_data: Dictionary containing context manager state
            console: Console instance for output

        Returns:
            Restored ContextManager instance or None if restoration failed
        """
        if not context_data:
            return None

        try:
            # Create a new context manager with saved parameters
            max_tokens = context_data.get("max_tokens")
            priority_mode = context_data.get("priority_mode")

            context_manager = ContextManager(
                max_tokens=max_tokens, priority_mode=priority_mode, console=console
            )

            # We don't restore the actual context items since they'll be rebuilt
            # when the conversation is loaded into run_conversation

            if DEBUG:
                self.console.print("[dim]Context manager restored from session[/dim]")

            return context_manager

        except Exception as e:
            if DEBUG:
                self.console.print(
                    f"[yellow]Error restoring context manager: {str(e)}[/yellow]"
                )
            return None


def recover_session(
    client: Any,  # Client implementation supporting LLM provider via litellm
    args,
    prompt_session: PromptSession,
    console: Console,
    permission_manager: Optional[Any] = None,
) -> bool:
    """
    Recover a previous session and continue the conversation.

    Args:
        client: Anthropic client instance
        args: Command line arguments
        prompt_session: PromptSession for input
        console: Console for output
        permission_manager: Optional permission manager for commands

    Returns:
        True if session was recovered and conversation started, False otherwise
    """
    from q_cli.cli.conversation import run_conversation
    from q_cli.utils.constants import MAX_HISTORY_TURNS, DEFAULT_MAX_TOKENS
    from q_cli.io.input import get_input

    # Make sure args has max_tokens attribute
    if not hasattr(args, "max_tokens"):
        args.max_tokens = DEFAULT_MAX_TOKENS

    # Create session manager
    session_manager = SessionManager(console)

    # Load session first to check if there's anything to recover
    conversation, system_prompt, context_data = session_manager.load_session(
        MAX_HISTORY_TURNS
    )

    if not conversation or not system_prompt:
        console.print("[yellow]No previous session found to recover[/yellow]")
        return False

    # Count available turns
    user_messages = [msg for msg in conversation if msg.get("role") == "user"]
    available_turns = len(user_messages)

    # Show session info
    last_user_msg = None
    last_assistant_msg = None

    for msg in reversed(conversation):
        if msg["role"] == "user" and not last_user_msg:
            last_user_msg = msg["content"]
        elif msg["role"] == "assistant" and not last_assistant_msg:
            last_assistant_msg = msg["content"]

        if last_user_msg and last_assistant_msg:
            break

    # Display recovery information
    console.print("[bold green]Recovering previous session[/bold green]")
    console.print(f"[dim]Found {len(conversation)} messages in the conversation[/dim]")
    console.print(f"[dim]Available conversation turns: {available_turns}[/dim]")

    if last_user_msg:
        console.print("[bold]Last user message:[/bold]")
        console.print(
            f"[dim]{last_user_msg[:100]}{'...' if len(last_user_msg) > 100 else ''}[/dim]"
        )

    # Ask for confirmation
    console.print(
        "\nType 'yes' to continue this conversation, or anything else to start fresh: "
    )

    # Use get_input from input module to handle possible EOFError
    confirm = get_input("", prompt_session).strip().lower()

    if confirm != "yes":
        console.print("[yellow]Session recovery cancelled[/yellow]")
        return False

    # Ask how many turns to recover
    turns_to_recover = MAX_HISTORY_TURNS
    if available_turns > 1:
        console.print(
            f"\n[bold]How many conversation turns would you like to recover (1-{available_turns})? [/bold]"
        )
        console.print(
            f"[dim]Default is {MAX_HISTORY_TURNS} if available, or all available turns otherwise.[/dim]"
        )

        turn_input = get_input("Turns to recover: ", prompt_session).strip()

        if turn_input:
            try:
                requested_turns = int(turn_input)
                if 1 <= requested_turns <= available_turns:
                    turns_to_recover = requested_turns
                else:
                    console.print(
                        f"[yellow]Invalid number. Using default ({min(MAX_HISTORY_TURNS, available_turns)} turns).[/yellow]"
                    )
                    turns_to_recover = min(MAX_HISTORY_TURNS, available_turns)
            except ValueError:
                console.print(
                    f"[yellow]Invalid input. Using default ({min(MAX_HISTORY_TURNS, available_turns)} turns).[/yellow]"
                )
                turns_to_recover = min(MAX_HISTORY_TURNS, available_turns)

    # Reload the session with the requested number of turns
    conversation, system_prompt, context_data = session_manager.load_session(
        turns_to_recover
    )

    # Restore context manager if data is available
    context_manager = (
        session_manager.restore_context_manager(context_data, console)
        if context_data
        else None
    )

    # Get an initial question to restart the conversation
    console.print(
        "[green]Session recovered. Type your next message to continue:[/green]"
    )

    # Use get_input from input module to handle possible EOFError
    initial_question = get_input("Q> ", prompt_session).strip()

    # Special handling for recovering via CLI flag: need to ensure initial_question isn't empty
    if args.recover and not initial_question:
        initial_question = " "  # Use a space to avoid empty input issues

    try:
        # Run the conversation with recovered data
        run_conversation(
            client=client,
            system_prompt=system_prompt,
            args=args,
            prompt_session=prompt_session,
            console=console,
            initial_question=initial_question,  # Use the new user input
            permission_manager=permission_manager,
            context_manager=context_manager,
            auto_approve=getattr(args, "yes", False),
            conversation=conversation,  # Pass existing conversation
            session_manager=session_manager,  # Pass session manager for continued saving
        )
    except Exception as e:
        console.print(f"[bold red]Error in conversation: {str(e)}[/bold red]")
        if DEBUG:
            import traceback

            console.print(f"[dim]{traceback.format_exc()}[/dim]")
        # Continue with error still counts as recovery
        return True

    return True
