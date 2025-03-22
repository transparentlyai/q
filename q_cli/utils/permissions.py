"""Command permission management for q_cli."""

import re
import shlex
from typing import Dict, List, Set, Tuple, Optional


class CommandPermissionManager:
    """
    Manages command execution permissions during a session.
    
    Handles:
    - Checking if commands are allowed, prohibited, or need permission
    - Tracking approved command categories for the session
    - Extracting command types from full command strings
    """
    
    def __init__(
        self,
        always_approved: Optional[List[str]] = None,
        always_restricted: Optional[List[str]] = None,
        prohibited: Optional[List[str]] = None
    ):
        """
        Initialize the permission manager with configured command lists.
        
        Args:
            always_approved: Commands that never require permission
            always_restricted: Commands that always require permission
            prohibited: Commands that can never be executed
        """
        # Convert all inputs to sets for efficient lookups
        self.always_approved_commands = set(always_approved or [])
        self.always_restricted_commands = set(always_restricted or [])
        self.prohibited_commands = set(prohibited or [])
        
        # Track commands approved during this session
        self.session_approved_commands: Set[str] = set()
    
    def extract_command_type(self, command: str) -> str:
        """
        Extract the base command type from a full command string.
        
        For example:
        - "cat file.txt" → "cat"
        - "ls -la /tmp" → "ls"
        - "find . -name '*.py'" → "find"
        
        Args:
            command: The full command string
            
        Returns:
            The base command executable
        """
        # Split the command, respecting quotes
        try:
            args = shlex.split(command)
            if not args:
                return ""
            
            # Get the first part as the command type
            base_cmd = args[0]
            
            # Handle command chains (cmd1 && cmd2, cmd1 | cmd2)
            # We extract only the first command for permission purposes
            for pattern in [" && ", " | ", " ; ", " || "]:
                if pattern in base_cmd:
                    base_cmd = base_cmd.split(pattern)[0].strip()
            
            # Strip any path components
            return base_cmd.split("/")[-1]
            
        except Exception:
            # If we can't parse it, just use the first word
            return command.strip().split()[0] if command.strip() else ""
    
    def is_command_prohibited(self, command: str) -> bool:
        """
        Check if a command is prohibited from execution.
        
        Args:
            command: The full command string
            
        Returns:
            True if the command is prohibited, False otherwise
        """
        cmd_type = self.extract_command_type(command)
        
        # Check if the command type is in the prohibited list
        if cmd_type in self.prohibited_commands:
            return True
        
        # Check if the full command matches any patterns in the prohibited list
        for pattern in self.prohibited_commands:
            if pattern.startswith("^") and pattern.endswith("$"):
                # Regex pattern
                if re.search(pattern, command):
                    return True
        
        return False
    
    def needs_permission(self, command: str) -> bool:
        """
        Check if a command needs permission before execution.
        
        Args:
            command: The full command string
            
        Returns:
            True if permission is needed, False if pre-approved
        """
        if not command.strip():
            return False
            
        cmd_type = self.extract_command_type(command)
        
        # First check if it's prohibited - if so, no need to check permission
        if self.is_command_prohibited(command):
            return False  # Will be blocked before permission check
        
        # Check if it's always approved
        if cmd_type in self.always_approved_commands:
            return False  # No permission needed
            
        # Check if it's already approved in this session
        if cmd_type in self.session_approved_commands:
            return False  # Already approved in this session
            
        # Always need permission for restricted commands
        if cmd_type in self.always_restricted_commands:
            return True  # Always need permission
            
        # By default, need permission for unrecognized commands
        return True
    
    def approve_command_type(self, command: str) -> None:
        """
        Mark a command type as approved for the rest of the session.
        
        Args:
            command: The command string to approve
        """
        cmd_type = self.extract_command_type(command)
        if cmd_type:
            self.session_approved_commands.add(cmd_type)
    
    @classmethod
    def from_config(cls, config_vars: Dict[str, str]) -> 'CommandPermissionManager':
        """
        Create a CommandPermissionManager from configuration variables.
        
        Args:
            config_vars: Dictionary of configuration variables
            
        Returns:
            Configured CommandPermissionManager instance
        """
        # Parse command lists from config
        always_approved = parse_command_list(config_vars.get("ALWAYS_APPROVED_COMMANDS", ""))
        always_restricted = parse_command_list(config_vars.get("ALWAYS_RESTRICTED_COMMANDS", ""))
        prohibited = parse_command_list(config_vars.get("PROHIBITED_COMMANDS", ""))
        
        # Create and return the manager
        return cls(
            always_approved=always_approved,
            always_restricted=always_restricted,
            prohibited=prohibited
        )


def parse_command_list(command_list_str: str) -> List[str]:
    """
    Parse a comma-separated or line-by-line list of commands.
    
    Args:
        command_list_str: String containing commands
        
    Returns:
        List of individual commands
    """
    if not command_list_str:
        return []
        
    # Handle both comma-separated and line-by-line formats
    if "," in command_list_str:
        # Comma-separated format
        commands = [cmd.strip() for cmd in command_list_str.split(",")]
    else:
        # Line-by-line format
        commands = [cmd.strip() for cmd in command_list_str.splitlines()]
        
    # Filter out empty strings
    return [cmd for cmd in commands if cmd]