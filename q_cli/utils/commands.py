"""Command execution functionality for q_cli."""

import os
import subprocess
import shlex
import re
from typing import Tuple, List, Optional
from rich.console import Console

from q_cli.utils.permissions import CommandPermissionManager

# List of potentially dangerous commands to block
BLOCKED_COMMANDS = [
    "rm -rf /",
    "sudo rm",
    "mkfs",
    "> /dev/sda",
    "dd if=/dev/zero",
    ":(){:|:&};:",
    "chmod -R 777 /",
]


def is_dangerous_command(command: str) -> bool:
    """Check if a command is potentially dangerous."""
    command_lower = command.lower()
    return any(blocked in command_lower for blocked in BLOCKED_COMMANDS)


def execute_command(command: str, console: Console) -> Tuple[int, str, str]:
    """
    Execute a shell command and return the results.

    Args:
        command: The command to execute
        console: Console for output

    Returns:
        Tuple containing (return_code, stdout, stderr)
    """
    # Check for dangerous commands
    if is_dangerous_command(command):
        return (-1, "", "This command has been blocked for security reasons.")

    try:
        # Execute the command and capture output
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Get output
        stdout, stderr = process.communicate(timeout=30)  # 30-second timeout
        return_code = process.returncode

        return (return_code, stdout, stderr)

    except subprocess.TimeoutExpired:
        return (-1, "", "Command timed out after 30 seconds")
    except Exception as e:
        return (-1, "", f"Error executing command: {str(e)}")


def format_command_output(return_code: int, stdout: str, stderr: str) -> str:
    """Format command output for display in the conversation."""
    output = f"Exit Code: {return_code}\n\n"

    if stdout:
        output += f"Output:\n```\n{stdout}\n```\n\n"

    if stderr:
        output += f"Errors:\n```\n{stderr}\n```"

    return output.strip()


def ask_command_confirmation(
    command: str, console: Console, permission_manager=None
) -> Tuple[bool, bool]:
    """
    Ask the user for confirmation before running a command.

    Args:
        command: The command to run
        console: Console for output
        permission_manager: Optional permission manager for tracking approvals

    Returns:
        Tuple containing:
        - Whether to execute this command (True/False)
        - Whether to remember this choice for similar commands (True/False)
    """
    # Check if we need to ask for permission
    if permission_manager and not permission_manager.needs_permission(command):
        return True, False  # Command is pre-approved, no need to remember

    # If command is prohibited, don't even ask
    if permission_manager and permission_manager.is_command_prohibited(command):
        console.print(
            f"\n[bold red]Command '{command}' is prohibited and cannot be executed.[/bold red]"
        )
        return False, False

    # Ask for user confirmation
    console.print(f"\n[bold yellow]Q wants to run this command:[/bold yellow]")
    console.print(f"[bold cyan]{command}[/bold cyan]")

    options = "[y/a/N] (y=yes, a=always, N=no): "
    response = input(f"\nExecute this command? {options}").lower().strip()

    if response.startswith("a"):
        # "Always" option - remember for the session
        return True, True

    return response.startswith("y"), False


def extract_commands_from_response(response: str) -> List[str]:
    """
    Extract commands from Q's response.

    Looks for commands formatted as:
    ```shell
    command here
    ```
    or
    ```bash
    command here
    ```
    Properly handles multi-line commands with backslashes.
    """
    commands = []

    # Find ```shell or ```bash blocks
    lines = response.split("\n")
    in_code_block = False
    is_shell_block = False
    current_block = []

    for line in lines:
        if line.strip().startswith("```") and not in_code_block:
            block_type = line.strip()[3:].lower()
            if block_type in ["shell", "bash", "sh", ""]:
                in_code_block = True
                is_shell_block = True
                continue
            else:
                in_code_block = True
                is_shell_block = False
                continue

        if line.strip() == "```" and in_code_block:
            in_code_block = False
            if is_shell_block and current_block:
                # Process the complete block now that we have all lines
                process_command_block(current_block, commands)
            current_block = []
            is_shell_block = False
            continue

        if in_code_block and is_shell_block:
            current_block.append(line)

    return commands


def is_line_continuation(line: str) -> bool:
    """
    Determine if a line ends with a backslash that indicates line continuation.

    Differentiates between escaped backslashes and continuation backslashes.

    Args:
        line: The line to check

    Returns:
        True if the line ends with a line continuation backslash, False otherwise
    """
    if not line.rstrip().endswith("\\"):
        return False

    # Count backslashes at the end of the line
    match = re.search(r"(\\+)$", line.rstrip())
    if not match:
        return False

    # If odd number of backslashes, it's a line continuation
    # If even, the last backslash is escaped
    backslash_count = len(match.group(1))
    return backslash_count % 2 == 1


def process_command_block(block_lines: List[str], commands: List[str]):
    """
    Process a block of shell commands, handling line continuations with backslashes.

    Distinguishes between:
    - Backslash as escape character (e.g., `echo \"hello\"`)
    - Backslash as line continuation marker

    Args:
        block_lines: List of lines from a code block
        commands: List to append extracted commands to
    """
    if not block_lines:
        return

    current_command = ""
    in_continuation = False

    for i, line in enumerate(block_lines):
        line = line.rstrip()

        if not line.strip():
            # Skip empty lines but preserve the current command
            continue

        if in_continuation:
            # This line is a continuation of the previous line
            current_command = current_command[:-1].rstrip() + " " + line.lstrip()
        else:
            # Not in continuation mode - if we have a stored command, add it
            if current_command:
                commands.append(current_command)
            current_command = line

        # Check if this line ends with a continuation marker
        in_continuation = is_line_continuation(line)

        # If this is the last line or not a continuation, add the command
        is_last_line = i == len(block_lines) - 1
        if is_last_line and current_command and not in_continuation:
            commands.append(current_command)

    # Add any remaining command that wasn't added yet
    if current_command and not in_continuation and current_command not in commands:
        commands.append(current_command)
