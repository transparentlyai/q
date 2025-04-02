"""Command permission management for q_cli."""

import json
import logging
import re
import shlex
import time
from typing import Dict, List, Set, Optional, Tuple, Any

from q_cli.utils.constants import DEBUG
from q_cli.utils.permissions_context import PermissionContextManager, ApprovalContext


class CommandPermissionManager:
    """
    Manages command execution permissions during a session.

    Handles:
    - Checking if commands are allowed, prohibited, or need permission
    - Tracking approved command categories for the session
    - Extracting command types from full command strings
    - Providing time-based and contextual approval management

    Permission Priority Order (highest to lowest):
    1. Prohibited commands - can never be executed
    2. Always restricted commands - always require explicit permission
    3. Contextual approvals - approved with time-based expirations
    4. Session approved commands - approved during the current session
    5. Always approved commands - pre-approved by default
    6. Default - require permission

    Note: Default commands from constants.py are always added to user-configured
    commands from the config file. This ensures core functionality while allowing
    user customization.
    """

    def __init__(
        self,
        always_approved: Optional[List[str]] = None,
        always_restricted: Optional[List[str]] = None,
        prohibited: Optional[List[str]] = None,
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
        
        # Context manager for time-based approvals
        self.context_manager = PermissionContextManager()

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

            # Strip any path components
            cmd_name = base_cmd.split("/")[-1]
            
            # Safety check: ensure we're not dealing with path traversal attempts
            if ".." in base_cmd:
                # Add special marker to indicate path traversal attempt
                return "PATH_TRAVERSAL_ATTEMPT"
                
            # Security improvement: normalize command name by removing
            # special characters, spaces, and ensuring lowercase for consistency
            cmd_name = cmd_name.lower().strip()
            
            return cmd_name

        except Exception:
            # If we can't parse it, just use the first word
            return command.strip().split()[0].lower() if command.strip() else ""

    def extract_all_command_types(self, command: str) -> List[str]:
        """
        Extract all command types from a complex command string.

        Handles:
        - Command chains (cmd1 && cmd2, cmd1 | cmd2, etc.)
        - Semicolon separators (cmd1; cmd2)
        - Find -exec commands
        - Command substitution ($(cmd) and `cmd`)

        Args:
            command: The full command string

        Returns:
            List of all command types found in the string
        """
        if not command.strip():
            return []

        command_types = []
        try:
            # First handle command separators to split into individual commands
            # Regex to identify shell separators while handling quoted sections
            parts = []
            current_part = ""
            in_quotes = False
            in_double_quotes = False
            in_backtick = False
            in_subshell = 0  # Counter for nested subshells
            i = 0

            while i < len(command):
                char = command[i]

                # Handle quotes
                if char == "'" and not in_double_quotes and not in_backtick:
                    in_quotes = not in_quotes
                elif char == '"' and not in_quotes and not in_backtick:
                    in_double_quotes = not in_double_quotes
                # Handle backticks for command substitution
                elif char == "`" and not in_quotes and not in_double_quotes:
                    in_backtick = not in_backtick
                    # When exiting backtick, we need to extract commands from within
                    if not in_backtick and "`" in current_part:
                        try:
                            # Find the last opening backtick
                            start_idx = current_part.rindex("`")

                            # Extract the backtick content - everything between the opening and current closing backtick
                            if (
                                start_idx < len(current_part) - 1
                            ):  # Make sure there's content inside
                                backtick_content = current_part[start_idx + 1 :]
                                # Recursively extract commands from backtick content
                                backtick_cmds = self.extract_all_command_types(
                                    backtick_content
                                )
                                command_types.extend(backtick_cmds)
                        except ValueError:
                            # If rindex fails, ignore this instance
                            pass
                # Handle subshell command substitution $(...)
                elif char == "$" and i + 1 < len(command) and command[i + 1] == "(":
                    in_subshell += 1
                    current_part += "$("
                    i += 1  # Skip the next character (the open parenthesis)
                elif char == ")" and in_subshell > 0:
                    in_subshell -= 1
                    current_part += ")"
                    # When exiting the outermost subshell, extract commands
                    if in_subshell == 0:
                        # Find the start of the subshell
                        start_idx = current_part.rindex("$(")
                        # Extract the subshell content
                        subshell_content = current_part[start_idx + 2 : -1]
                        # Recursively extract commands from subshell content
                        subshell_cmds = self.extract_all_command_types(subshell_content)
                        command_types.extend(subshell_cmds)
                # Handle command separators when not in quotes, backticks, or subshells
                elif (
                    (
                        char == ";"
                        or (
                            char == "&"
                            and i + 1 < len(command)
                            and command[i + 1] == "&"
                        )
                        or (
                            char == "|"
                            and i + 1 < len(command)
                            and command[i + 1] == "|"
                        )
                        or char == "|"
                    )
                    and not in_quotes
                    and not in_double_quotes
                    and not in_backtick
                    and in_subshell == 0
                ):

                    if (
                        char in ("&", "|")
                        and i + 1 < len(command)
                        and command[i + 1] == char
                    ):
                        # Handle && and ||
                        parts.append(current_part.strip())
                        current_part = ""
                        i += 1  # Skip the next character
                    else:
                        # Handle ; and |
                        parts.append(current_part.strip())
                        current_part = ""
                else:
                    current_part += char

                i += 1

            # Add the last part if there's any
            if current_part.strip():
                parts.append(current_part.strip())

            # Process each command part
            for part in parts:
                if part:
                    # Handle find -exec commands
                    if part.startswith("find") and "-exec" in part:
                        # Extract the command after -exec
                        exec_idx = part.find("-exec")
                        if exec_idx != -1:
                            # Find the command after -exec
                            exec_part = part[exec_idx + 5 :].strip()
                            # The command is everything until the next {} or \;
                            exec_end = exec_part.find("{}")
                            if exec_end == -1:
                                exec_end = exec_part.find("\\;")
                            if exec_end != -1:
                                exec_cmd = exec_part[:exec_end].strip()
                                if exec_cmd:
                                    exec_cmds = self.extract_all_command_types(exec_cmd)
                                    command_types.extend(exec_cmds)

                    # Extract the base command from this part
                    cmd_type = self.extract_command_type(part)
                    if cmd_type:
                        command_types.append(cmd_type)

            return command_types

        except Exception as e:
            # If parsing fails, try a simpler approach
            import re

            # Try to extract commands from backticks
            backtick_matches = re.findall(r"`([^`]+)`", command)
            for backtick in backtick_matches:
                backtick_content = backtick.strip()
                if backtick_content:
                    # Try to get the first word as a command
                    backtick_cmd = (
                        backtick_content.split()[0] if backtick_content.split() else ""
                    )
                    if backtick_cmd and backtick_cmd not in command_types:
                        command_types.append(backtick_cmd)

                    # Also check if the backtick content itself contains common dangerous commands
                    for dangerous_cmd in [
                        "rm",
                        "mv",
                        "cp",
                        "sudo",
                        "chmod",
                        "chown",
                        "dd",
                        "mkfs",
                    ]:
                        if re.search(r"\b" + dangerous_cmd + r"\b", backtick_content):
                            if dangerous_cmd not in command_types:
                                command_types.append(dangerous_cmd)

            # Simple regex to find common dangerous commands
            common_cmds = re.findall(
                r"\b(rm|mv|cp|sudo|chmod|chown|dd|mkfs|poweroff|halt|shutdown)\b",
                command,
            )
            for cmd in common_cmds:
                if cmd not in command_types:
                    command_types.append(cmd)

            return command_types

    def is_command_prohibited(self, command: str) -> bool:
        """
        Check if a command is prohibited from execution.

        Args:
            command: The full command string

        Returns:
            True if the command is prohibited, False otherwise
        """
        # Special check for backtick with prohibited commands
        for prohibited in self.prohibited_commands:
            if isinstance(prohibited, str) and not prohibited.startswith("^"):
                # Check for the prohibited command inside backticks
                backtick_pattern = r"`[^`]*\b" + re.escape(prohibited) + r"\b[^`]*`"
                if re.search(backtick_pattern, command):
                    return True

        # Extract all command types from the command string
        cmd_types = self.extract_all_command_types(command)

        # Also get the basic first command (for backwards compatibility)
        first_cmd_type = self.extract_command_type(command)
        if first_cmd_type not in cmd_types and first_cmd_type:
            cmd_types.append(first_cmd_type)

        # Check if any command type is in the prohibited list
        for cmd_type in cmd_types:
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

        Priority order (from highest to lowest):
        1. Prohibited commands - always blocked (returns False)
        2. Always restricted commands - always need permission
        3. Time-based contextual approvals - can be approved with expiration
        4. Session approved commands - approved for this session
        5. Always approved commands - pre-approved in config

        Args:
            command: The full command string

        Returns:
            True if permission is needed, False if pre-approved
        """
        if not command.strip():
            return False

        # First check if it's prohibited - if so, no need to check permission
        if self.is_command_prohibited(command):
            return False  # Will be blocked before permission check

        # Global approval check - if active and valid, bypass all checks
        if self.context_manager.global_approval and self.context_manager.global_approval.is_valid:
            if DEBUG:
                from rich.console import Console
                console = Console()
                console.print(f"[yellow]DEBUG: Command '{command}' approved via global approval context[/yellow]")
            return False  # No permission needed, globally approved

        # Extract all command types from the command string
        cmd_types = self.extract_all_command_types(command)

        # Also get the basic first command (for backwards compatibility)
        first_cmd_type = self.extract_command_type(command)
        if first_cmd_type not in cmd_types and first_cmd_type:
            cmd_types.append(first_cmd_type)

        # Check for exact command match in contextual approvals
        if self.context_manager.is_command_approved(command, first_cmd_type):
            if DEBUG:
                from rich.console import Console
                console = Console()
                console.print(f"[yellow]DEBUG: Command '{command}' approved via contextual approval[/yellow]")
            return False  # No permission needed, contextually approved

        # Check if any command is restricted
        for cmd_type in cmd_types:
            # Always need permission for restricted commands (highest priority after prohibited)
            if cmd_type in self.always_restricted_commands:
                return True  # Always need permission

            # Check if command type is approved in context
            if cmd_type in self.context_manager.type_approvals and self.context_manager.type_approvals[cmd_type].is_valid:
                continue  # Type is approved in context, check next type
                
            # If any command type is not pre-approved in any way, we need permission
            if (
                cmd_type not in self.session_approved_commands
                and cmd_type not in self.always_approved_commands
            ):
                return True

        # If we get here, all commands are either context-approved, session-approved or always-approved
        return False

    def approve_command_type(self, command: str, timeout: Optional[int] = None, context: str = "") -> None:
        """
        Mark a command type as approved with optional time-based expiration.

        Args:
            command: The command string to approve
            timeout: Optional timeout in seconds for this approval
            context: Optional context description for this approval
        """
        # For complex commands, we need to approve all command types
        # Extract all command types and add them to the session approved list
        cmd_types = self.extract_all_command_types(command)

        # For backwards compatibility, also get the basic first command
        first_cmd_type = self.extract_command_type(command)
        if first_cmd_type not in cmd_types and first_cmd_type:
            cmd_types.append(first_cmd_type)

        # If timeout is specified, use contextual approvals
        if timeout is not None:
            # Add all command types to the contextual approval list
            for cmd_type in cmd_types:
                if cmd_type:
                    self.context_manager.approve_command_type(cmd_type, timeout, context)
        else:
            # Add all command types to the session approved list (permanent for this session)
            for cmd_type in cmd_types:
                if cmd_type:
                    self.session_approved_commands.add(cmd_type)
                    
    def approve_command(self, command: str, timeout: Optional[int] = None, context: str = "") -> None:
        """
        Approve a specific command with optional time-based expiration.
        
        Args:
            command: The exact command to approve
            timeout: Optional timeout in seconds for this approval
            context: Optional context description for this approval
        """
        if timeout is not None:
            self.context_manager.approve_command(command, timeout, context)
        # No else clause - we don't have persistent approval for exact commands
        
    def approve_all(self, timeout: Optional[int] = None, context: str = "") -> None:
        """
        Approve all commands temporarily with a timeout.
        
        Args:
            timeout: Timeout in seconds for global approval (default: 30 minutes)
            context: Optional context description for this approval
        """
        self.context_manager.approve_all(timeout, context)

    @classmethod
    def from_config(cls, config_vars: Dict[str, str]) -> "CommandPermissionManager":
        """
        Create a CommandPermissionManager from configuration variables.

        Args:
            config_vars: Dictionary of configuration variables

        Returns:
            Configured CommandPermissionManager instance
        """
        # Parse command lists from config
        always_approved = parse_command_list(
            config_vars.get("ALWAYS_APPROVED_COMMANDS", "")
        )
        always_restricted = parse_command_list(
            config_vars.get("ALWAYS_RESTRICTED_COMMANDS", "")
        )
        prohibited = parse_command_list(config_vars.get("PROHIBITED_COMMANDS", ""))

        # Create and return the manager
        return cls(
            always_approved=always_approved,
            always_restricted=always_restricted,
            prohibited=prohibited,
        )


def parse_command_list(command_list_str: str) -> List[str]:
    """
    Parse commands from a JSON array string.
    Command lists must be specified in JSON array format on a single line.

    Args:
        command_list_str: String containing commands in JSON array format

    Returns:
        List of individual commands
    """
    if not command_list_str:
        return []

    command_list_str = command_list_str.strip()

    # Parse as JSON with strict validation
    if command_list_str.startswith("[") and command_list_str.endswith("]"):
        try:
            # Parse the JSON data with strict parsing enabled
            result = json.loads(command_list_str, strict=True)
            
            # Validate the result is a list and all elements are strings
            if not isinstance(result, list):
                logging.warning(f"Command list must be a JSON array, got {type(result).__name__}")
                return []
                
            # Filter out any non-string elements
            string_items = []
            for item in result:
                if isinstance(item, str):
                    string_items.append(item)
                else:
                    logging.warning(f"Ignoring non-string command: {item}")
            
            return string_items
        except json.JSONDecodeError as e:
            # Log an error but return empty list
            logging.warning(f"Error parsing command list JSON: {e}")
            return []
    else:
        # Not a valid JSON array format
        logging.warning(
            f"Invalid command list format. Must be a JSON array: {command_list_str}"
        )
        return []
