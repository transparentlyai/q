"""Command execution functionality for q_cli."""

import os
import subprocess
import shlex
import re
import tempfile
from typing import Tuple, List, Optional, Dict, Any
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

    # Check if this is a heredoc command
    heredoc_match = re.search(r'<<\s*[\'"]*([^\'"\s<]*)[\'"]*', command)
    if heredoc_match:
        console.print(
            "[yellow]Heredoc commands (with <<EOF) are not directly supported.[/yellow]"
        )
        console.print("[yellow]Use the file creation interface instead.[/yellow]")
        return (-1, "", "Heredoc commands are not supported for direct execution.")

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
    # Check for heredoc pattern before anything else
    heredoc_match = re.search(r'<<\s*[\'"]*([^\'"\s<]*)[\'"]*', command)
    if heredoc_match:
        console.print(f"\n[bold yellow]Q suggested a heredoc command:[/bold yellow]")
        console.print(f"[bold cyan]{command}[/bold cyan]")
        console.print("[yellow]Heredoc commands cannot be executed directly.[/yellow]")
        console.print(
            "[yellow]Use the 'cat > file' command followed by a separate content block instead.[/yellow]"
        )
        return False, False

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


def ask_execution_plan_confirmation(
    commands: List[str], console: Console, permission_manager=None
) -> Tuple[bool, List[int]]:
    """
    Present the full execution plan and ask for user confirmation.
    
    Args:
        commands: List of commands to execute
        console: Console for output
        permission_manager: Optional permission manager for tracking approvals
        
    Returns:
        Tuple containing:
        - Whether to execute any commands (True/False)
        - List of indices of commands to execute
    """
    if not commands:
        return False, []
        
    # Filter out prohibited commands and special file creation commands
    executable_commands = []
    command_indices = []
    
    for i, command in enumerate(commands):
        # Skip empty commands
        if not command.strip():
            continue
            
        # Skip special file creation commands for now
        if command.startswith("__FILE_CREATION__"):
            executable_commands.append(f"Create file (special command)")
            command_indices.append(i)
            continue
            
        # Skip prohibited commands
        if permission_manager and permission_manager.is_command_prohibited(command):
            console.print(
                f"\n[bold red]Command '{command}' is prohibited and cannot be executed.[/bold red]"
            )
            continue
            
        # Include all other commands
        executable_commands.append(command)
        command_indices.append(i)
        
    if not executable_commands:
        console.print("\n[yellow]No executable commands in the plan.[/yellow]")
        return False, []
        
    # Present the execution plan
    console.print("\n[bold blue]Command Execution Plan:[/bold blue]")
    # Print the first command
    if executable_commands:
        console.print(f"\n[bold]1.[/bold] [cyan]{executable_commands[0]}[/cyan]")
        # Print the rest without extra newlines
        for i, cmd in enumerate(executable_commands[1:], start=2):
            console.print(f"[bold]{i}.[/bold] [cyan]{cmd}[/cyan]")
        
    # Ask if we should execute the commands
    console.print("\n[bold yellow]Do you approve executing these commands?[/bold yellow]")
    options = "[y/n] (y=yes, n=no): "
    response = input(f"\nApprove commands? {options}").lower().strip()
    
    if response.startswith("y"):
        # Execute commands
        return True, command_indices
    else:
        # Don't execute any commands
        return False, []


def is_file_creation_command(command: str) -> Dict[str, Any]:
    """
    Detect if a command is trying to create a file using a heredoc or similar.

    Args:
        command: The command string to analyze

    Returns:
        Dictionary with command information:
        - 'is_file_creation': bool - True if this is a file creation command
        - 'file_path': str - Path to the file (if detected)
        - 'method': str - Method used ('heredoc', 'cat', etc.)
        - 'delimiter': str - Delimiter for heredoc (if applicable)
    """
    result = {
        "is_file_creation": False,
        "file_path": None,
        "method": None,
        "delimiter": None,
    }

    # Check for heredoc pattern: cat > file << 'EOF' or cat > file << EOF
    heredoc_pattern = (
        r'(?:cat|tee)\s+(?:>>?)\s+([^\s<]+)\s*<<\s*[\'"]*([^\'"\s]*)[\'"]*'
    )
    match = re.match(heredoc_pattern, command)

    if match:
        result["is_file_creation"] = True
        result["file_path"] = match.group(1)
        result["method"] = "heredoc"
        result["delimiter"] = match.group(2)
        return result

    # Check for simple file creation pattern: cat > file
    simple_cat_pattern = r"(?:cat|tee)\s+(?:>>?)\s+([^\s<]+)"
    match = re.match(simple_cat_pattern, command)

    if match:
        result["is_file_creation"] = True
        result["file_path"] = match.group(1)
        result["method"] = "cat"
        return result

    return result


def extract_file_content_for_command(command: Dict[str, Any], response: str) -> str:
    """
    Extract content intended for a file from code blocks in the response.

    This function looks for a non-shell code block following a file creation command
    in the response, assuming it contains the content intended for the file.

    Args:
        command: Command info dictionary from is_file_creation_command
        response: The full response from Q

    Returns:
        Content for the file, or empty string if none found
    """
    if not command["is_file_creation"]:
        return ""

    # Find the code blocks in the response
    lines = response.split("\n")
    in_code_block = False
    current_block_content = []
    found_blocks = []

    for line in lines:
        if line.strip().startswith("```") and not in_code_block:
            # Start of a code block
            in_code_block = True
            block_type = line.strip()[3:].lower()
            current_block_content = []
            continue

        if line.strip() == "```" and in_code_block:
            # End of a code block
            in_code_block = False
            # Save the complete block
            found_blocks.append("\n".join(current_block_content))
            continue

        if in_code_block:
            current_block_content.append(line)

    # If we have code blocks, return the largest one (most likely the file content)
    if found_blocks:
        # Sort blocks by size and return the largest one
        return max(found_blocks, key=len)

    return ""


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

    Also looks for file content in other code blocks for file creation commands.
    """
    commands = []
    file_creation_commands = []

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

    # Post-process commands to handle file creation
    processed_commands = []
    for cmd in commands:
        file_info = is_file_creation_command(cmd)
        if file_info["is_file_creation"]:
            # Mark this as a file creation command with its details
            file_creation_commands.append((cmd, file_info))
        else:
            processed_commands.append(cmd)

    # Handle file creation commands
    for cmd, file_info in file_creation_commands:
        # Try to find content for this file in the response
        content = extract_file_content_for_command(file_info, response)

        if content:
            # Store the original command and the intended content as metadata
            cmd_with_metadata = f"__FILE_CREATION__{file_info['file_path']}__DELIMITER__{file_info['delimiter']}__CONTENT__{content}"
            processed_commands.append(cmd_with_metadata)
        else:
            # If no content found, keep the original command
            processed_commands.append(cmd)

    return processed_commands


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


def handle_file_creation_command(
    command: str, console: Console
) -> Tuple[bool, str, str]:
    """
    Handle a special file creation command, extracting metadata and creating the file.

    Args:
        command: The command string with file creation metadata
        console: Console for output

    Returns:
        Tuple of (success, stdout, stderr)
    """
    # Extract metadata from the command
    parts = command.split("__")
    if len(parts) < 7:
        return False, "", "Invalid file creation command format"

    # Extract file path, delimiter, and content
    try:
        file_path = parts[2]
        delimiter = parts[4]
        content = "__".join(parts[6:])  # Join in case content contains "__"
    except IndexError:
        return False, "", "Failed to parse file creation command"

    # Show the file details and content to the user
    console.print(
        f"\n[bold yellow]Q wants to create a file at:[/bold yellow] {file_path}"
    )
    console.print("[bold yellow]Here's the content of the file:[/bold yellow]")
    console.print(f"```\n{content}\n```")

    # Ask for confirmation
    response = (
        input(f"\nCreate file '{file_path}' with this content? [y/N]: ").lower().strip()
    )
    if not response.startswith("y"):
        console.print("[yellow]File creation skipped by user[/yellow]")
        return False, "", "File creation skipped by user"

    # Create the file
    try:
        # Create parent directories if they don't exist
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)

        with open(file_path, "w") as f:
            f.write(content)

        console.print(f"[green]File created successfully: {file_path}[/green]")
        return True, f"File created: {file_path}", ""
    except Exception as e:
        error_msg = f"Error creating file: {str(e)}"
        console.print(f"[red]{error_msg}[/red]")
        return False, "", error_msg


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
