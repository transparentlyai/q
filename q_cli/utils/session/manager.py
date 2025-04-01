"""Session management for Q conversations."""

import os
import json
import time
import tempfile
import mmap
from typing import Dict, List, Optional, Any, Tuple
from rich.console import Console
import anthropic
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
                    self.console.print(f"[dim]Created session directory: {session_dir}[/dim]")
            except Exception as e:
                self.console.print(f"[yellow]Warning: Could not create session directory: {e}[/yellow]")
    
    def save_session(
        self, 
        conversation: List[Dict[str, Any]], 
        system_prompt: str,
        context_manager: Optional[ContextManager] = None
    ) -> bool:
        """
        Save the current conversation session to a file.
        
        Args:
            conversation: List of conversation messages
            system_prompt: The system prompt used in the conversation
            context_manager: Optional context manager instance
        
        Returns:
            True if session was saved successfully, False otherwise
        """
        try:
            # Create session data structure
            session_data = {
                "timestamp": time.time(),
                "conversation": conversation,
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
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
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
    
    def load_session(self) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str], Optional[Dict]]:
        """
        Load a previously saved conversation session.
        
        Returns:
            Tuple containing:
            - List of conversation messages (or None if not found)
            - System prompt (or None if not found)
            - Context data dictionary (or None if not found)
        """
        if not os.path.exists(self.session_file):
            if DEBUG:
                self.console.print(f"[yellow]No session file found at {self.session_file}[/yellow]")
            return None, None, None
        
        try:
            # Use memory mapping for efficient loading of large files
            with open(self.session_file, 'r+') as f:
                # Get file size
                file_size = os.path.getsize(self.session_file)
                
                if file_size > 0:
                    # For small files, read directly
                    if file_size < 10_000_000:  # 10MB threshold
                        session_data = json.load(f)
                    else:
                        # For large files, use memory mapping
                        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                            session_json = mm.read().decode('utf-8')
                            session_data = json.loads(session_json)
                    
                    conversation = session_data.get("conversation", [])
                    system_prompt = session_data.get("system_prompt", "")
                    context_data = session_data.get("context_data", None)
                    
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
                self.console.print(f"[yellow]Corrupted session file backed up to {backup_file}[/yellow]")
            except Exception:
                pass
                
            return None, None, None

    def restore_context_manager(
        self, 
        context_data: Dict, 
        console: Console
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
                max_tokens=max_tokens,
                priority_mode=priority_mode,
                console=console
            )
            
            # We don't restore the actual context items since they'll be rebuilt
            # when the conversation is loaded into run_conversation
            
            if DEBUG:
                self.console.print("[dim]Context manager restored from session[/dim]")
                
            return context_manager
            
        except Exception as e:
            if DEBUG:
                self.console.print(f"[yellow]Error restoring context manager: {str(e)}[/yellow]")
            return None


def recover_session(
    client: anthropic.Anthropic,
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
    
    # Create session manager
    session_manager = SessionManager(console)
    
    # Load session
    conversation, system_prompt, context_data = session_manager.load_session()
    
    if not conversation or not system_prompt:
        console.print("[yellow]No previous session found to recover[/yellow]")
        return False
        
    # Restore context manager if data is available
    context_manager = session_manager.restore_context_manager(context_data, console) if context_data else None
    
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
    
    if last_user_msg:
        console.print("[bold]Last user message:[/bold]")
        console.print(f"[dim]{last_user_msg[:100]}{'...' if len(last_user_msg) > 100 else ''}[/dim]")
        
    # Ask for confirmation
    console.print("\nType 'yes' to continue this conversation, or anything else to start fresh: ", end="")
    confirm = input().strip().lower()
    
    if confirm != "yes":
        console.print("[yellow]Session recovery cancelled[/yellow]")
        return False
        
    # Run the conversation with recovered data
    # Pass empty string as initial question since we're restoring from saved state
    run_conversation(
        client=client,
        system_prompt=system_prompt,
        args=args,
        prompt_session=prompt_session,
        console=console,
        initial_question="",  # Empty since we're restoring existing conversation
        permission_manager=permission_manager,
        context_manager=context_manager,
        auto_approve=getattr(args, "yes", False),
        conversation=conversation,  # Pass existing conversation
        session_manager=session_manager  # Pass session manager for continued saving
    )
    
    return True