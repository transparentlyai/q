"""Command execution functionality for q_cli."""

import os
import subprocess
import re
import difflib
import mimetypes
import shlex
from typing import Tuple, List, Dict, Any, Optional, Union
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table
from colorama import Fore, Style
from q_cli.utils.constants import get_debug, MAX_FILE_DISPLAY_LENGTH

# Global flag for "approve all" operations that persists between function calls
# This is set to True when user selects "a" option and ensures all subsequent operations
# are auto-approved without asking again
GLOBAL_APPROVE_ALL = False

# Define the special formats for file writing and command execution
WRITE_FILE_MARKER_START = 'Q:COMMAND type="write" path='
WRITE_FILE_MARKER_END = "/Q:COMMAND"
RUN_SHELL_MARKER_START = 'Q:COMMAND type="shell"'
RUN_SHELL_MARKER_END = "/Q:COMMAND"
URL_BLOCK_MARKER = 'Q:COMMAND type="fetch"'  # Match the block marker in web.py
READ_FILE_MARKER_START = 'Q:COMMAND type="read"'
READ_FILE_MARKER_END = "/Q:COMMAND"

# List of potentially dangerous commands to block
BLOCKED_COMMANDS = [
    # File system destruction commands
    "rm -rf /", "rm -rf /*", "rm -rf .", "rm -fr /", "rm -fr /*",
    # Disk overwrite commands
    "> /dev/sda", "> /dev/hda", "dd if=/dev/zero", "mkfs", "format", 
    # Privilege escalation
    "sudo rm", "sudo chmod", "sudo chown", "sudo dd", "sudo mkfs",
    # System modification
    "chmod -R 777 /", "chmod 777 -R /", "chmod -R 777 .", 
    # Fork bombs and resource exhaustion
    ":(){:|:&};:", "while true; do", ":(){ :|: & };:",
    # Network attacks
    "wget -O- | bash", "curl | bash", "curl | sh", "wget -O- | sh",
    # System control commands
    "shutdown", "reboot", "halt", "poweroff",
    # Dangerous pipe sequences
    "> /dev", "> /proc", "dd if="
]


def is_dangerous_command(command: str) -> bool:
    """Check if a command is potentially dangerous."""
    command_lower = command.lower()
    return any(blocked in command_lower for blocked in BLOCKED_COMMANDS)


def execute_command(command: str, console: Console, skip_dangerous_check: bool = False) -> Tuple[int, str, str]:
    """
    Execute a shell command and return the results.

    Args:
        command: The command to execute
        console: Console for output
        skip_dangerous_check: Whether to skip the dangerous command check (if already approved via permission system)

    Returns:
        Tuple containing (return_code, stdout, stderr)
    """
    # Debug output
    if get_debug():
        console.print(f"[yellow]Executing command: {command}[/yellow]")

    # Check for dangerous commands - but skip if the command was already approved by permission manager
    if not skip_dangerous_check and is_dangerous_command(command):
        if get_debug():
            console.print(
                f"[yellow]Command blocked as dangerous: {command}[/yellow]"
            )
        return (-1, "", "This command has been blocked for security reasons.")

    # Check if this is a heredoc command
    heredoc_match = re.search(r'<<\s*[\'"]*([^\'"\s<]*)[\'"]*', command)
    if heredoc_match:
        if get_debug():
            console.print(
                f"[yellow]Heredoc command detected: {command}[/yellow]"
            )
            console.print(
                "[yellow]Heredoc commands (with <<EOF) are not directly supported.[/yellow]"
            )
            console.print("[yellow]Use the file creation interface instead.[/yellow]")
        return (-1, "", "Heredoc commands are not supported for direct execution.")
    
    # More thorough security check: split command to get executable and prevent path traversal
    try:
        args = shlex.split(command)
        if not args:
            return (-1, "", "Empty command")
            
        # Get the first part as the base command
        base_cmd = args[0]
        
        # If command contains a path, make sure it doesn't include path traversal
        if '/' in base_cmd and '..' in base_cmd:
            return (-1, "", "Path traversal attempts are not allowed")
            
    except Exception as e:
        if get_debug():
            console.print(f"[yellow]Command parsing error: {str(e)}[/yellow]")
        return (-1, "", f"Error parsing command: {str(e)}")

    try:
        # Execute the command and capture output
        if get_debug():
            console.print(f"[yellow]Starting subprocess for: {command}[/yellow]")
        process = subprocess.Popen(
            command,
            shell=True,  # Note: shell=True is still a potential risk but permission system mitigates this
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # No need to explicitly mention Ctrl+C here

        try:
            # Get output with timeout
            stdout, stderr = process.communicate(timeout=30)  # 30-second timeout
            return_code = process.returncode
        except KeyboardInterrupt:
            # Handle Ctrl+C during command execution
            try:
                # Try to terminate the process group to kill child processes too
                process.terminate()
                process.wait(timeout=2)  # Give it a moment to terminate gracefully
            except:
                # If it doesn't terminate, try to kill
                try:
                    process.kill()
                    process.wait(timeout=1)
                except:
                    pass  # Already dead or can't be killed

            console.print("\n[bold red]Command interrupted by user[/bold red]")
            # Return interrupt code with STOP message for operations
            return (
                -1,
                "",
                "STOP. The operation was cancelled by user. Do not proceed with any additional commands or operations. Wait for new instructions from the user.",
            )

        if get_debug():
            console.print(
                f"[yellow]Command completed with return code: {return_code}[/yellow]"
            )
            if stdout and len(stdout) > 0:
                console.print(
                    f"[yellow]Command stdout length: {len(stdout)} bytes[/yellow]"
                )
            if stderr and len(stderr) > 0:
                console.print(
                    f"[yellow]Command stderr length: {len(stderr)} bytes[/yellow]"
                )

        return (return_code, stdout, stderr)

    except subprocess.TimeoutExpired:
        if get_debug():
            console.print(f"[yellow]Command timed out: {command}[/yellow]")
        return (-1, "", "Command timed out after 30 seconds")
    except Exception as e:
        if get_debug():
            console.print(f"[yellow]Command error: {str(e)}[/yellow]")
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
        - Whether to remember this choice for similar commands (True/False) or "approve_all" for global approval
    """
    # Check for heredoc pattern before anything else
    heredoc_match = re.search(r'<<\s*[\'"]*([^\'"\s<]*)[\'"]*', command)
    if heredoc_match:
        if get_debug():
            console.print("\n[yellow]Q suggested a heredoc command:[/yellow]")
            console.print(f"[yellow]{command}[/yellow]")
            console.print(
                "[yellow]Heredoc commands cannot be executed directly.[/yellow]"
            )
            console.print(
                "[yellow]Use the 'cat > file' command followed by a separate content block instead.[/yellow]"
            )
        return False, False

    # Check if we need to ask for permission
    if permission_manager and not permission_manager.needs_permission(command):
        # Get context if available for debug output
        if get_debug():
            context = None
            try:
                context = permission_manager.context_manager.get_approval_context(command, 
                                                                                 permission_manager.extract_command_type(command))
                if context:
                    remaining = int(context.time_remaining)
                    console.print(f"[yellow]Command pre-approved with {remaining} seconds remaining[/yellow]")
            except Exception:
                pass
        return True, False  # Command is pre-approved, no need to remember

    # If command is prohibited, don't even ask
    if permission_manager and permission_manager.is_command_prohibited(command):
        if get_debug():
            console.print(
                f"[yellow]Command '{command}' is prohibited and cannot be executed.[/yellow]"
            )
        return False, False

    # Ask for user confirmation
    console.print("\n[bold yellow]Q wants to run this command:[/bold yellow]")
    console.print(f"[bold cyan]{command}[/bold cyan]")

    options = "[y/a/t/Y/N/c] (y=yes, a=approve all for 30m, t=timed approval, Y=yes+remember for session, N=no, c=cancel): "
    response = input("\nExecute this command? " + options).lower().strip()

    if response == "c":
        # "Cancel" option - cancel the operation completely
        console.print(f"[bold red]Operation cancelled by user[/bold red]")
        # We use a special marker "cancel_all" to indicate nothing should be sent to Claude
        return "cancel_all", False
    elif response == "a":
        # "Approve all" option with default timeout (30 minutes)
        if permission_manager:
            # Use contextual time-based approval system
            permission_manager.approve_all(timeout=None, context="User selected 'approve all'")
            console.print(f"[bold green]Approve-all mode activated for 30 minutes. All operations will be approved automatically.[/bold green]")
        else:
            console.print(f"[bold green]Approve-all mode activated. All operations will be approved automatically.[/bold green]")
        # Return special flag to the caller
        return True, "approve_all"
    elif response == "t":
        # Timed approval with custom timeout
        try:
            timeout_input = input("Enter approval timeout in minutes (default: 30): ").strip()
            if not timeout_input:
                timeout = 30 * 60  # Default 30 minutes in seconds
            else:
                timeout = int(timeout_input) * 60  # Convert minutes to seconds
                
            if permission_manager:
                # Get command type for more focused approval
                cmd_type = permission_manager.extract_command_type(command)
                options = input("Approve only this command (c), all commands of this type (t), or all commands (a)? [c/t/a]: ").strip().lower()
                
                if options == "c":
                    # Approve just this specific command
                    permission_manager.approve_command(command, timeout=timeout, context=f"User approved for {timeout_input} minutes")
                    console.print(f"[bold green]Command '{command}' approved for {timeout//60} minutes.[/bold green]")
                elif options == "a":
                    # Approve all commands
                    permission_manager.approve_all(timeout=timeout, context=f"User approved all for {timeout_input} minutes")
                    console.print(f"[bold green]All commands approved for {timeout//60} minutes.[/bold green]")
                else:
                    # Default: approve this command type
                    permission_manager.approve_command_type(command, timeout=timeout, context=f"User approved {cmd_type} for {timeout_input} minutes")
                    console.print(f"[bold green]Command type '{cmd_type}' approved for {timeout//60} minutes.[/bold green]")
            else:
                console.print(f"[bold yellow]No permission manager available for timed approval. Approving this command only.[/bold yellow]")
        except ValueError:
            console.print(f"[bold yellow]Invalid timeout value. Using default 30 minutes.[/bold yellow]")
            timeout = 30 * 60
            if permission_manager:
                permission_manager.approve_command_type(command, timeout=timeout)
        
        return True, False  # Execute but don't set global remember flag
    elif response.startswith("y") and len(response) > 1:
        # "Always" option - remember this command type for the entire session (no timeout)
        return True, True
    
    # Regular yes (or any other response starting with y)
    return response.startswith("y"), False


def extract_code_blocks(response: str) -> Dict[str, List[List[str]]]:
    """
    Extract all code blocks from a response, categorized by block type.
    Specially handles Q:COMMAND blocks to avoid treating them as commands.

    Args:
        response: The response text

    Returns:
        Dictionary mapping block types (shell, bash, etc.) to lists of blocks
    """
    blocks: Dict[str, List[List[str]]] = {"shell": [], "other": []}

    # First, check if there are any command markers in the response
    has_command_markers = "<Q:COMMAND" in response

    # First let's extract all regular code blocks using the traditional format
    lines = response.split("\n")
    in_code_block = False
    current_type = ""
    current_block: List[str] = []
    skip_line = False  # To skip lines that might be part of command markers

    for line in lines:
        # If we see a command marker, skip this line
        if "<Q:COMMAND" in line or "</Q:COMMAND>" in line:
            skip_line = True
            continue

        # Skip line if we're in skip mode
        if skip_line:
            # End skip mode if we've reached the end of a command block
            if "</Q:COMMAND>" in line:
                skip_line = False
            continue

        if line.strip().startswith("```") and not in_code_block:
            # Start of a code block
            block_type = line.strip()[3:].lower()
            in_code_block = True
            current_type = (
                "shell" if block_type in ["shell", "bash", "sh", ""] else "other"
            )
            current_block = []
            continue

        if line.strip() == "```" and in_code_block:
            # End of a code block
            in_code_block = False
            if current_block:  # Only add non-empty blocks
                # Extra check to avoid command markers in shell blocks
                if current_type == "shell" and any(
                    "<Q:COMMAND" in line for line in current_block
                ):
                    # Skip this block or convert to "other" type if it contains command markers
                    blocks["other"].append(current_block)
                else:
                    blocks[current_type].append(current_block)
            current_block = []
            continue

        if in_code_block:
            current_block.append(line)

    return blocks


def extract_shell_markers_from_response(response: str) -> List[Tuple[str, str]]:
    """
    Extract shell command markers from the model's response.

    Format:
    - <Q:COMMAND type="shell">
      command
      </Q:COMMAND>

    Args:
        response: The model's response text

    Returns:
        List of tuples containing (command, original_marker)
    """
    # Regular expression to match the shell command format
    pattern = re.compile(
        r"<Q:COMMAND type=\"shell\">\s*(.*?)\s*</Q:COMMAND>", re.DOTALL
    )

    matches = []

    for match in pattern.finditer(response):
        command = match.group(1).strip()
        original_marker = match.group(0)

        # For XML-like tags we don't need to check for nested code blocks
        matches.append((command, original_marker))

    return matches


def remove_special_markers(response: str) -> str:
    """
    Remove all special command markers from the model's response.

    Args:
        response: The raw response from the model

    Returns:
        Response with all special markers removed
    """
    # Remove shell command markers
    pattern = re.compile(
        r"<Q:COMMAND type=\"shell\">\s*(.*?)\s*</Q:COMMAND>", re.DOTALL
    )
    cleaned = pattern.sub("", response)

    # Remove file writing markers
    pattern = re.compile(
        r'<Q:COMMAND type="write" path="(.*?)">\s*(.*?)\s*</Q:COMMAND>', re.DOTALL
    )
    cleaned = pattern.sub("", cleaned)

    # Remove URL fetch markers
    pattern = re.compile(
        r"<" + re.escape(URL_BLOCK_MARKER) + r">\s*(.*?)\s*</Q:COMMAND>", re.DOTALL
    )
    cleaned = pattern.sub("", cleaned)
    
    # Remove file reading markers
    pattern = re.compile(
        r"<" + re.escape(READ_FILE_MARKER_START) + r">\s*(.*?)\s*</Q:COMMAND>", re.DOTALL
    )
    cleaned = pattern.sub("", cleaned)

    # Clean up any leftover open/close tags
    leftover_markers = [
        "<Q:COMMAND",
        "</Q:COMMAND>",
    ]

    for marker in leftover_markers:
        cleaned = cleaned.replace(marker, "")

    # Clean up excessive newlines (more than 2 consecutive newlines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned


def extract_commands_from_response(response: str) -> List[str]:
    """
    Extract commands from Q's response.

    Uses Q:COMMAND markers to identify commands within the XML-like format:
    <Q:COMMAND type="shell">
    command to execute
    </Q:COMMAND>

    Filters out any lines that match the WRITE_FILE pattern to avoid treating them as commands.
    """
    # First check if this response contains file operation results
    # If so, completely skip command extraction for safety
    file_op_indicators = ["[File written:", "[Failed to write file:"]

    if any(indicator in response for indicator in file_op_indicators):
        # This response includes file operation results - don't extract commands
        return []

    commands = []

    # Extract commands using shell command markers
    shell_markers = extract_shell_markers_from_response(response)
    for command, _ in shell_markers:
        commands.append(command)

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


def extract_file_markers_from_response(response: str) -> List[Tuple[str, str, str]]:
    """
    Extract file writing markers from the model's response.

    Format:
    - <Q:COMMAND type="write" path="path/to/file">
      content
      </Q:COMMAND>

    Args:
        response: The model's response text

    Returns:
        List of tuples containing (file_path, content, original_marker)
    """
    matches = []

    # Regular expression to match the file writing XML-like format
    pattern = re.compile(
        r'<Q:COMMAND type="write" path="(.*?)">\s*(.*?)\s*</Q:COMMAND>', re.DOTALL
    )

    for match in pattern.finditer(response):
        file_path = match.group(1).strip()
        content = match.group(2)
        original_marker = match.group(0)

        # For XML-like tags we don't need to check for nested code blocks
        matches.append((file_path, content, original_marker))

    return matches


def extract_read_file_markers_from_response(response: str) -> List[Tuple[str, str]]:
    """
    Extract file reading markers from the model's response.

    Format:
    - <Q:COMMAND type="read">
      path/to/file
      </Q:COMMAND>

    Args:
        response: The model's response text

    Returns:
        List of tuples containing (file_path, original_marker)
    """
    matches = []

    # Regular expression to match the file reading XML-like format
    pattern = re.compile(
        r'<Q:COMMAND type="read">\s*(.*?)\s*</Q:COMMAND>', re.DOTALL
    )

    for match in pattern.finditer(response):
        file_path = match.group(1).strip()
        original_marker = match.group(0)

        # For XML-like tags we don't need to check for nested code blocks
        matches.append((file_path, original_marker))

    return matches


def show_diff(old_content: str, new_content: str, console: Console) -> None:
    """
    Display a colored diff between old and new content.

    Args:
        old_content: Original file content
        new_content: New content to be written
        console: Console for output
    """
    # Get the diff
    diff = list(
        difflib.unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            lineterm="",
            n=3,  # Context lines
        )
    )

    if not diff:
        console.print("[yellow]No changes detected in file content[/yellow]")
        return

    # Create a table for the diff display
    table = Table(title="File Changes", expand=True, box=None)
    table.add_column("Diff", no_wrap=True)

    # Add each line with appropriate coloring
    for line in diff:
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            # Header lines in blue
            table.add_row(f"[blue]{line}[/blue]")
        elif line.startswith("+"):
            # Added lines in green
            table.add_row(f"[green]{line}[/green]")
        elif line.startswith("-"):
            # Removed lines in red
            table.add_row(f"[red]{line}[/red]")
        else:
            # Context lines in normal color
            table.add_row(line)

    console.print(table)


def read_file_from_marker(
    file_path: str, console: Console
) -> Tuple[bool, str, str, Optional[str], Optional[bytes]]:
    """
    Read content from a file based on a file reading marker.

    Args:
        file_path: Path of the file to read
        console: Console for output

    Returns:
        Tuple containing (success, stdout, stderr, file_type, binary_content)
        binary_content is only provided for non-text files
    """
    try:
        if get_debug():
            console.print(
                f"[yellow]Reading file from marker: {file_path}[/yellow]"
            )

        # Expand the file path (handle ~ and environment variables)
        expanded_path = os.path.expanduser(file_path)
        expanded_path = os.path.expandvars(expanded_path)

        if get_debug():
            console.print(f"[yellow]Expanded path: {expanded_path}[/yellow]")

        # Make sure the path is relative to the current working directory if not absolute
        if not os.path.isabs(expanded_path):
            expanded_path = os.path.join(os.getcwd(), expanded_path)
            if get_debug():
                console.print(f"[yellow]Absolute path: {expanded_path}[/yellow]")
                
        # Security: Validate the path doesn't use path traversal to escape current directory
        cwd = os.getcwd()
        try:
            # Use os.path.realpath to resolve any symbolic links and normalize the path
            real_path = os.path.realpath(expanded_path)
            
            # Check if path is within current directory tree or user's home directory
            in_current_dir = real_path.startswith(os.path.realpath(cwd))
            in_home_dir = real_path.startswith(os.path.realpath(os.path.expanduser("~")))
            
            if not (in_current_dir or in_home_dir):
                # Path is outside of safe directories
                if get_debug():
                    console.print(f"[yellow]Path traversal attempt - path points outside of allowed directories: {real_path}[/yellow]")
                return False, "", "Operation rejected: For security reasons, file operations are restricted to the current directory and home directory.", None, None
                
            if get_debug():
                console.print(f"[yellow]Validated safe path: {real_path}[/yellow]")
                
        except Exception as e:
            if get_debug():
                console.print(f"[yellow]Path validation error: {str(e)}[/yellow]")
            return False, "", f"Error validating path: {str(e)}", None, None

        # Check if file exists
        if not os.path.exists(expanded_path):
            error_msg = f"File not found: {expanded_path}"
            console.print(f"[red]{error_msg}[/red]")
            return False, "", error_msg, None, None

        # Get file size for information
        file_size = os.path.getsize(expanded_path)
        file_info = f"Read file: {expanded_path} ({file_size} bytes)"
        
        # Use python-magic for robust file type detection
        try:
            import magic
            file_type = magic.from_file(expanded_path)
            mime_type = magic.from_file(expanded_path, mime=True)
            
            if get_debug():
                console.print(f"[yellow]Magic detected type: {file_type}[/yellow]")
                console.print(f"[yellow]Magic detected MIME: {mime_type}[/yellow]")
            
            # Check if it's a text file based on mime type and description
            is_text_file = mime_type.startswith('text/') or \
                any(t in mime_type for t in ['json', 'xml', 'javascript', 'yaml', 'html']) or \
                "ASCII text" in file_type or "UTF-8 text" in file_type or \
                "Unicode text" in file_type or "script" in file_type
                
            # Special case for Dockerfiles
            filename = os.path.basename(expanded_path)
            if filename.lower() == "dockerfile" or filename.lower().endswith("dockerfile"):
                is_text_file = True
                
        except ImportError:
            # Fallback to extension-based detection if python-magic is not available
            file_ext = os.path.splitext(expanded_path)[1].lower()
            mime_type_result = mimetypes.guess_type(expanded_path)[0]
            mime_type = mime_type_result if mime_type_result is not None else ""
            
            if get_debug():
                console.print(f"[yellow]Magic not available, using extension-based detection[/yellow]")
                console.print(f"[yellow]Extension: {file_ext}, MIME: {mime_type}[/yellow]")
            
            # Determine if this is a text file or binary file based on extension
            text_extensions = ['.txt', '.md', '.py', '.js', '.html', '.css', '.json', '.xml', 
                              '.yml', '.yaml', '.toml', '.ini', '.csv', '.sh', '.bat', '.c', 
                              '.cpp', '.h', '.java', '.rs', '.go', '.ts', '.jsx', '.tsx',
                              '.dockerfile', '.gitignore', '.env']
            
            is_text_file = file_ext in text_extensions or mime_type.startswith('text/')
            
            # Special case for Dockerfiles
            filename = os.path.basename(expanded_path)
            if filename.lower() == "dockerfile" or filename.lower().endswith("dockerfile"):
                is_text_file = True
        
        # Try to read as text first
        try:
            if is_text_file:
                with open(expanded_path, "r", encoding="utf-8") as f:
                    content = f.read()
                # Show success message
                console.print(f"[bold green]Text file read successfully: {expanded_path}[/bold green]")
                return True, f"{file_info}\n\n{content}", "", "text", None
            else:
                # This is a binary/image file, read it as binary
                with open(expanded_path, "rb") as f:
                    binary_content = f.read()
                
                # Check if this is a PDF file
                is_pdf = mime_type == "application/pdf" or expanded_path.lower().endswith('.pdf')
                
                # Use magic to detect if this is an image (ensure mime_type is not None)
                is_image = bool(mime_type and mime_type.startswith('image/'))
                
                # Fallback to extension check if magic doesn't identify it as an image
                if not is_image:
                    file_ext = os.path.splitext(expanded_path)[1].lower()
                    image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg']
                    is_image = file_ext in image_extensions
                
                if is_pdf:
                    if get_debug():
                        console.print(f"[yellow]PDF file detected, processing with PDF module: {expanded_path}[/yellow]")
                    
                    # Handle PDF with specialized PDF module
                    try:
                        from q_cli.utils.pdf import extract_text_from_pdf, check_dependencies
                        
                        # Check if PDF dependencies are installed
                        deps_installed, error_msg = check_dependencies()
                        if not deps_installed:
                            if get_debug():
                                console.print(f"[yellow]{error_msg}[/yellow]")
                            console.print(f"[bold green]PDF file read as text (missing PDF libraries): {expanded_path}[/bold green]")
                            return True, file_info, "", "text", None
                        
                        # Extract text and tables from PDF
                        success, pdf_text, _ = extract_text_from_pdf(expanded_path, console)
                        if success:
                            console.print(f"[bold green]PDF processed successfully: {expanded_path}[/bold green]")
                            # Only return text, not binary content
                            return True, f"{file_info}\n\n{pdf_text}", "", "text", None
                        else:
                            # Fallback to binary handling if extraction fails
                            console.print(f"[bold green]PDF file read as binary (extraction failed): {expanded_path}[/bold green]")
                            # Try to extract as text anyway
                            return True, file_info, "", "text", None
                    except ImportError:
                        # PDF module not available or dependencies missing
                        if get_debug():
                            console.print(f"[yellow]PDF module not available, handling as binary[/yellow]")
                        console.print(f"[bold green]PDF file read as text: {expanded_path}[/bold green]")
                        return True, file_info, "", "text", None
                
                elif is_image:
                    console.print(f"[bold green]Image file read successfully: {expanded_path}[/bold green]")
                    # Return metadata for multimodal handling
                    return True, file_info, "", "image", binary_content
                else:
                    # For other binary files
                    console.print(f"[bold green]Binary file read successfully: {expanded_path}[/bold green]")
                    # Return binary data for potential multimodal handling 
                    return True, file_info, "", "binary", binary_content
                    
        except UnicodeDecodeError:
            # Fallback: Read as binary if text read fails
            try:
                # We thought it was text, but it failed to decode - read as binary
                with open(expanded_path, "rb") as f:
                    binary_content = f.read()
                
                # Double-check with magic if we have it
                try:
                    import magic
                    mime_type = magic.from_buffer(binary_content, mime=True)
                    file_type = magic.from_buffer(binary_content)
                    
                    # Check if it's an image despite the decode error
                    is_image = bool(mime_type and mime_type.startswith('image/'))
                    
                    if is_image:
                        console.print(f"[bold green]Image file read successfully: {expanded_path}[/bold green]")
                        return True, file_info, "", "image", binary_content
                    
                    if get_debug():
                        console.print(f"[yellow]UnicodeDecodeError but magic says: {file_type}[/yellow]")
                except ImportError:
                    # No magic available, just continue with binary handling
                    pass
                    
                console.print(f"[bold green]Binary file read successfully: {expanded_path}[/bold green]")
                return True, file_info, "", "binary", binary_content
            except Exception as e:
                error_msg = f"Error reading file: {str(e)}"
                console.print(f"[red]{error_msg}[/red]")
                return False, "", error_msg, None, None
        except Exception as e:
            error_msg = f"Error reading file: {str(e)}"
            console.print(f"[red]{error_msg}[/red]")
            return False, "", error_msg, None, None

    except Exception as e:
        error_msg = f"Error reading file: {str(e)}"
        # Only show error details in debug mode
        if get_debug():
            console.print(f"[yellow]{error_msg}[/yellow]")
            import traceback
            console.print(f"[yellow]{traceback.format_exc()}[/yellow]")
        # Make sure this detailed error is returned so it can be sent to the model
        return False, "", error_msg, None, None


def write_file_from_marker(
    file_path: str, content: str, console: Console, auto_approve: bool = False, 
    approve_all: bool = False, permission_manager=None
) -> Tuple[bool, str, Union[str, bool]]:
    """
    Write content to a file based on a file writing marker.

    Args:
        file_path: Path where the file should be written
        content: Content to write to the file
        console: Console for output
        auto_approve: Whether to automatically approve file operations (from command line)
        approve_all: Whether to approve all file operations in this session
        permission_manager: Optional permission manager for contextual approvals

    Returns:
        Tuple containing:
        - success: Whether the operation succeeded
        - stdout: Output message
        - stderr_or_approve_all: Either error message or True if "approve all" was selected
    """
    # Check for contextual approval if we have a permission manager
    has_context_approval = False
    if permission_manager and permission_manager.context_manager:
        # Check for global approvals (time-based)
        if permission_manager.context_manager.global_approval and permission_manager.context_manager.global_approval.is_valid:
            has_context_approval = True
            if get_debug():
                remaining = int(permission_manager.context_manager.global_approval.time_remaining)
                console.print(f"[yellow]File operation auto-approved via global context (remaining: {remaining}s)[/yellow]")
    
    # Use either the command-line auto_approve, approve_all flag, or contextual approval
    effective_approve_all = auto_approve or approve_all or has_context_approval
    
    if get_debug() and effective_approve_all:
        console.print(f"[yellow]Auto-approving file operations (auto_approve={auto_approve}, approve_all={approve_all}, context_approval={has_context_approval})[/yellow]")
    try:
        if get_debug():
            console.print(
                f"[yellow]Writing file from marker: {file_path}[/yellow]"
            )
            console.print(
                f"[yellow]Content length: {len(content)} bytes[/yellow]"
            )

        # Expand the file path (handle ~ and environment variables)
        expanded_path = os.path.expanduser(file_path)
        expanded_path = os.path.expandvars(expanded_path)

        if get_debug():
            console.print(f"[yellow]Expanded path: {expanded_path}[/yellow]")

        # Make sure the path is relative to the current working directory if not absolute
        if not os.path.isabs(expanded_path):
            expanded_path = os.path.join(os.getcwd(), expanded_path)
            if get_debug():
                console.print(f"[yellow]Absolute path: {expanded_path}[/yellow]")
                
        # Security: Validate the path doesn't use path traversal to escape current directory
        cwd = os.getcwd()
        try:
            # Use os.path.realpath to resolve any symbolic links and normalize the path
            real_path = os.path.realpath(expanded_path)
            
            # Check if path is within current directory tree or user's home directory
            in_current_dir = real_path.startswith(os.path.realpath(cwd))
            in_home_dir = real_path.startswith(os.path.realpath(os.path.expanduser("~")))
            
            if not (in_current_dir or in_home_dir):
                # Path is outside of safe directories
                if get_debug():
                    console.print(f"[yellow]Path traversal attempt - path points outside of allowed directories: {real_path}[/yellow]")
                return False, "", "Operation rejected: For security reasons, file operations are restricted to the current directory and home directory."
                
            if get_debug():
                console.print(f"[yellow]Validated safe path: {real_path}[/yellow]")
                
        except Exception as e:
            if get_debug():
                console.print(f"[yellow]Path validation error: {str(e)}[/yellow]")
            return False, "", f"Error validating path: {str(e)}"

        # Ensure the directory exists
        directory = os.path.dirname(expanded_path)
        if directory and not os.path.exists(directory):
            if get_debug():
                console.print(
                    f"[yellow]Creating directory: {directory}[/yellow]"
                )
            os.makedirs(directory, exist_ok=True)

        # Check if file already exists to show diff
        existing_content = ""
        is_overwrite = os.path.exists(expanded_path)
        if is_overwrite:
            try:
                with open(expanded_path, "r", encoding="utf-8") as f:
                    existing_content = f.read()
            except Exception as e:
                if get_debug():
                    console.print(
                        f"[yellow]Could not read existing file: {str(e)}[/yellow]"
                    )

        # Ensure the content maintains consistent newlines
        # Normalize line endings to platform-specific newlines
        if content and "\r\n" in content and os.name != "nt":
            # Convert Windows line endings to Unix for non-Windows platforms
            content = content.replace("\r\n", "\n")
        elif content and "\n" in content and os.name == "nt":
            # Convert Unix line endings to Windows for Windows platforms
            if not content.endswith("\r\n") and "\r\n" not in content:
                content = content.replace("\n", "\r\n")

        if get_debug():
            console.print(
                f"[yellow]Content size after newline normalization: {len(content)} bytes[/yellow]"
            )

        # Show the file details to the user
        console.print("")  # Add spacing for better readability

        if is_overwrite:
            console.print(
                f"[bold yellow]Q wants to MODIFY an existing file:[/bold yellow] {expanded_path}"
            )
            console.print("[bold yellow]Here's what will change:[/bold yellow]")
            show_diff(existing_content, content, console)
        else:
            console.print(
                f"[bold yellow]Q wants to create a new file:[/bold yellow] {expanded_path}"
            )
            console.print(
                f"[bold yellow]Content length:[/bold yellow] {len(content)} bytes"
            )

            # Truncate content for display if it's too long
            if len(content) > MAX_FILE_DISPLAY_LENGTH:
                display_content = (
                    content[:MAX_FILE_DISPLAY_LENGTH] + "\n[...content truncated...]"
                )
                console.print(
                    "[bold yellow]Here's a preview of the file content:[/bold yellow]"
                )
            else:
                display_content = content
                console.print(
                    "[bold yellow]Here's the content of the file:[/bold yellow]"
                )

            # For syntax highlighting, try to detect the language from the file extension
            try:
                ext = os.path.splitext(expanded_path)[1].lstrip(".").lower()
                if ext in [
                    "py",
                    "js",
                    "java",
                    "c",
                    "cpp",
                    "go",
                    "rs",
                    "sh",
                    "md",
                    "html",
                    "css",
                    "json",
                ]:
                    syntax = Syntax(
                        display_content, ext, theme="monokai", line_numbers=True
                    )
                    console.print(syntax)
                else:
                    console.print(f"```\n{display_content}\n```")
            except Exception:
                console.print(f"```\n{display_content}\n```")

        # No longer showing interrupt hint

        try:
            # Set default response
            response = ""

            # Auto-approve if command line flag OR approve-all mode is active
            if auto_approve or effective_approve_all:
                response = "y"  # Auto-approve
                action = "Modifying" if is_overwrite else "Creating"
                console.print(f"[bold green]Auto-approved:[/bold green] {action} file '{expanded_path}'")
            else:
                # Ask for confirmation with appropriate message
                if is_overwrite:
                    prompt = f"\nMODIFY file '{expanded_path}' with the changes shown above? [y=yes, n=no, r=rename, a=approve all, c=cancel] "
                else:
                    prompt = f"\nCreate file '{expanded_path}' with this content? [y=yes, n=no, r=rename, a=approve all, c=cancel] "

                response = input(prompt).lower().strip()
                
                # Check if user selected "cancel"
                if response.startswith("c"):
                    # Cancel the entire operation
                    console.print(f"[bold red]Operation cancelled by user[/bold red]")
                    # Use "cancel_all" as a special marker that nothing should be sent to Claude
                    return "cancel_all", "", ""
                
                # Check if user selected "approve all"
                if response.startswith("a"):
                    response = "y"  # Treat as yes for this file
                    
                    # If we have a permission manager, use time-based approval system
                    if permission_manager:
                        # Use default timeout (30 minutes)
                        permission_manager.approve_all(
                            timeout=None, 
                            context="User selected 'approve all' during file operations"
                        )
                        console.print(f"[bold green]▶▶▶ Time-based approve-all mode activated for 30 minutes. All operations will be approved automatically.[/bold green]")
                    else:
                        # Fall back to old behavior if no permission manager
                        # CRITICAL: Set the GLOBAL flag to ensure all future operations are approved
                        # (note: global statements must be at the function level, not in a conditional)
                        global GLOBAL_APPROVE_ALL
                        GLOBAL_APPROVE_ALL = True
                        console.print(f"[bold green]▶▶▶ Approve-all mode activated. All file operations will be approved automatically.[/bold green]")
                    
                    # Write the file now
                    directory = os.path.dirname(expanded_path)
                    if directory and not os.path.exists(directory):
                        os.makedirs(directory, exist_ok=True)
                    
                    with open(expanded_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    
                    # Return and signal that approve_all was activated
                    action = "updated" if is_overwrite else "created"
                    return True, f"File {action}: {expanded_path}", True

                # Option to save with a different filename
                if response.startswith("r"):
                    new_filename = input("\nEnter new filename: ").strip()
                    if not new_filename:
                        error_msg = "File writing skipped - no filename provided"
                        if get_debug():
                            console.print(f"[yellow]{error_msg}[/yellow]")
                        return False, "", error_msg

                    # Expand the new file path
                    if not os.path.isabs(new_filename):
                        # If relative path, keep it in the same directory as the original
                        new_filename = os.path.join(
                            os.path.dirname(expanded_path), new_filename
                        )
                    else:
                        # If absolute path, use it as is
                        new_filename = os.path.expanduser(new_filename)
                        new_filename = os.path.expandvars(new_filename)

                    # Set the new path and reset overwrite flag
                    expanded_path = new_filename
                    is_overwrite = os.path.exists(expanded_path)

                    # Ensure the directory exists for the new path
                    directory = os.path.dirname(expanded_path)
                    if directory and not os.path.exists(directory):
                        os.makedirs(directory, exist_ok=True)

                    # Show confirmation of the new path
                    console.print(
                        f"[bold yellow]Will write to new path: {expanded_path}[/bold yellow]"
                    )

                    # Ask for final confirmation with the new path
                    confirm = (
                        input(f"Proceed with writing to {expanded_path}? [y=yes, N=no, c=cancel] ")
                        .lower()
                        .strip()
                    )
                    if confirm.startswith("c"):
                        # Cancel the entire operation
                        console.print(f"[bold red]Operation cancelled by user[/bold red]")
                        # Use "cancel_all" as a special marker that nothing should be sent to Claude
                        return "cancel_all", "", ""
                    elif not confirm.startswith("y"):
                        error_msg = "File writing skipped by user"
                        if get_debug():
                            console.print(f"[yellow]{error_msg}[/yellow]")
                        return False, "", error_msg
                elif not response.startswith("y"):
                    error_msg = "File writing skipped by user"
                    # Only show error details in debug mode
                    if get_debug():
                        console.print(f"[yellow]{error_msg}[/yellow]")
                    # Make sure this error is returned so it can be sent to the model
                    return False, "", error_msg
        except KeyboardInterrupt:
            # Handle Ctrl+C during confirmation
            console.print("\n[bold red]File operation interrupted by user[/bold red]")
            return (
                False,
                "",
                "STOP. The operation was cancelled by user. Do not proceed with any additional commands or operations. Wait for new instructions from the user.",
            )

        # Write the file atomically to prevent truncation if interrupted
        if get_debug():
            console.print(
                f"[yellow]Writing content to file: {expanded_path}[/yellow]"
            )
            console.print(
                f"[yellow]Content length for writing: {len(content)} bytes[/yellow]"
            )

        try:
            # Write to a temporary file first, then atomically rename to the target
            import tempfile
            import shutil
            import uuid

            # Create a temporary file in the same directory for atomic move
            temp_dir = os.path.dirname(expanded_path) or "."
            temp_base = f".{os.path.basename(expanded_path)}.{uuid.uuid4().hex}"
            temp_path = os.path.join(temp_dir, temp_base)

            try:
                # Ensure the temp file has the same permissions as the target would
                # if we're overwriting an existing file
                if is_overwrite and os.path.exists(expanded_path):
                    # Copy existing file's permissions, ownership, etc.
                    shutil.copy2(expanded_path, temp_path)
                    # Then open for writing (which truncates it)
                    with open(temp_path, "w", encoding="utf-8") as f:
                        f.write(content)
                        f.flush()  # Ensure data is written to disk
                        os.fsync(f.fileno())  # Force flush to disk
                else:
                    # No existing file, just create a new one
                    with open(temp_path, "w", encoding="utf-8") as f:
                        f.write(content)
                        f.flush()  # Ensure data is written to disk
                        os.fsync(f.fileno())  # Force flush to disk

                # Double check file was written correctly
                if os.path.exists(temp_path):
                    with open(temp_path, "r", encoding="utf-8") as f:
                        written_content = f.read()
                    if len(written_content) != len(content):
                        raise IOError(
                            f"Temporary file size mismatch: written {len(written_content)}, expected {len(content)}"
                        )

                # Now atomically move the temp file to the target
                shutil.move(temp_path, expanded_path)

                if get_debug():
                    console.print(
                        f"[yellow]File written successfully via atomic operation[/yellow]"
                    )
            finally:
                # Clean up the temp file if it still exists
                if os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        pass
        except KeyboardInterrupt:
            # Handle Ctrl+C during file writing
            console.print("\n[bold red]File writing interrupted by user[/bold red]")
            console.print(
                "[yellow]Original file is preserved due to atomic writing[/yellow]"
            )
            return (
                False,
                "",
                "STOP. The operation was cancelled by user. Do not proceed with any additional commands or operations. Wait for new instructions from the user.",
            )

        # Show success message more prominently
        action = "updated" if is_overwrite else "created"
        console.print(
            f"[bold green]File {action} successfully: {expanded_path}[/bold green]"
        )
        console.print("")  # Add empty line after success message
        if get_debug():
            console.print(
                f"[green]File write successful: {expanded_path}[/green]"
            )
            
        # Return approve_all status in third position
        if approve_all or effective_approve_all:
            # Return True to indicate approve_all is active
            return True, f"File {action}: {expanded_path}", True
        else:
            # Normal operation - return empty string for stderr
            return True, f"File {action}: {expanded_path}", ""

    except Exception as e:
        error_msg = f"Error writing file: {str(e)}"
        # Only show error details in debug mode
        if get_debug():
            console.print(f"[yellow]{error_msg}[/yellow]")
            import traceback

            console.print(f"[yellow]{traceback.format_exc()}[/yellow]")
        # Make sure this detailed error is returned so it can be sent to the model
        return False, "", error_msg


def process_file_reads(
    response: str,
    console: Console,
    show_errors: bool = True,
) -> Tuple[str, List[Dict[str, Any]], bool, List[Dict[str, Any]]]:
    """
    Process a response from the model, handling any file reading markers.

    Args:
        response: The model's response text
        console: Console for output
        show_errors: Whether to display error messages to the user

    Returns:
        Tuple containing:
        - Processed response with file reading markers replaced
        - List of dictionaries with file reading results (text)
        - Boolean indicating if any errors occurred
        - List of dictionaries with multimodal file results (images/binary)
    """
    # Extract all file reading markers
    if get_debug():
        console.print(
            "[yellow]Looking for file reading markers in response[/yellow]"
        )
    file_matches = extract_read_file_markers_from_response(response)

    if not file_matches:
        if get_debug():
            console.print("[yellow]No file reading markers found[/yellow]")
        return response, [], False, []

    if get_debug():
        console.print(
            f"[yellow]Found {len(file_matches)} file reading markers[/yellow]"
        )
        # Log details about each file marker
        for idx, (file_path, _) in enumerate(file_matches):
            console.print(
                f"[yellow]Marker {idx+1}: Path={file_path}[/yellow]"
            )

    processed_response = response
    file_results = []
    multimodal_results = []
    has_error = False

    for file_path, original_marker in file_matches:
        success, stdout, stderr, file_type, binary_content = read_file_from_marker(file_path, console)

        # Track if any operations failed
        if not success:
            has_error = True

        # Create a basic result entry
        result = {
            "file_path": file_path,
            "success": success,
            "stdout": stdout,
            "stderr": stderr,
        }
        
        # Handle multimodal content (images, PDFs, binary files)
        if success and binary_content:
            mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
            
            # Check if PDF specifically 
            is_pdf = mime_type == "application/pdf" or file_path.lower().endswith('.pdf')
            
            # Only include images in multimodal content (not PDFs)
            if file_type == "image":
                multimodal_result = {
                    "file_path": file_path,
                    "file_type": "image",
                    "content": binary_content,
                    "mime_type": mime_type
                }
                multimodal_results.append(multimodal_result)
            elif file_type == "binary" and DEBUG:
                console.print(f"[yellow]Binary file {file_path} not sent as multimodal content[/yellow]")
            
            # For multimodal files, we only include basic info in the regular results
            # The actual binary content will be handled via multimodal messaging
            file_results.append(result)
        else:
            # For text files or failures, proceed as normal
            file_results.append(result)

        # Use a clean, user-friendly replacement format that won't be interpreted as commands
        # but still provides information about the file operation result
        if success:
            replacement = f"[File read: {file_path}]"
        else:
            replacement = f"[Failed to read file: {file_path}]"

        # Find the original marker in the response
        marker_start = processed_response.find(original_marker)
        if marker_start != -1:
            # Simple replacement - keep any text after the marker
            processed_response = processed_response.replace(
                original_marker, replacement
            )
        else:
            # Normal replacement as fallback
            processed_response = processed_response.replace(
                original_marker, replacement
            )

    return processed_response, file_results, has_error, multimodal_results


def process_file_writes(
    response: str,
    console: Console,
    show_errors: bool = True,
    auto_approve: bool = False,
    approve_all: bool = False,
    permission_manager=None,
) -> Tuple[str, List[Dict[str, Any]], bool]:
    """
    Process a response from the model, handling any file writing markers.

    Args:
        response: The model's response text
        console: Console for output
        show_errors: Whether to display error messages to the user
        auto_approve: Whether to automatically approve all file operations (from command line)
        approve_all: Whether to approve all file operations in this session
        permission_manager: Optional permission manager for contextual approvals

    Returns:
        Tuple containing:
        - Processed response with file writing markers replaced
        - List of dictionaries with file writing results
        - Boolean indicating if any errors occurred
    """
    # Use passed approve_all flag
    use_approve_all = approve_all
    
    # Extract all file writing markers
    if get_debug():
        console.print(
            "[yellow]Looking for file writing markers in response[/yellow]"
        )
    file_matches = extract_file_markers_from_response(response)

    if not file_matches:
        if get_debug():
            console.print("[yellow]No file writing markers found[/yellow]")
        return response, [], False

    if get_debug():
        console.print(
            f"[yellow]Found {len(file_matches)} file writing markers[/yellow]"
        )
        # Log details about each file marker
        for idx, (file_path, content, _) in enumerate(file_matches):
            console.print(
                f"[yellow]Marker {idx+1}: Path={file_path}, Content length={len(content)} bytes[/yellow]"
            )

    processed_response = response
    file_results = []
    has_error = False

    # Process each file
    for file_path, content, original_marker in file_matches:
            
        # Call write_file_from_marker with current approve_all status and permission manager
        success, stdout, result = write_file_from_marker(
            file_path, content, console, auto_approve, use_approve_all, permission_manager
        )

        # Check if approve_all was activated 
        if success and result is True:
            # User selected "approve all" or it was already active
            use_approve_all = True
            
            # If we have a permission manager, use its time-based approval method
            if permission_manager:
                # Default timeout is 30 minutes
                permission_manager.approve_all(timeout=None, context="User selected 'approve all' during file operations")
                if get_debug():
                    console.print(f"[yellow]Activated time-based approval for all operations (30 minutes)[/yellow]")
                    
            stderr = ""  # No error
        else:
            # Normal case (not approve_all), stderr was returned
            stderr = result
            
        # Track if any operations failed
        if not success:
            has_error = True

        result = {
            "file_path": file_path,
            "success": success,
            "stdout": stdout,
            "stderr": stderr,
        }
        file_results.append(result)

        # Use a clean, user-friendly replacement format that won't be interpreted as commands
        # but still provides information about the file operation result
        if success:
            replacement = f"[File written: {file_path}]"
        else:
            replacement = f"[Failed to write file: {file_path}]"

        # Find the original marker in the response
        marker_start = processed_response.find(original_marker)
        if marker_start != -1:
            # Simple replacement - keep any text after the marker
            processed_response = processed_response.replace(
                original_marker, replacement
            )
        else:
            # Normal replacement as fallback
            processed_response = processed_response.replace(
                original_marker, replacement
            )

    # We no longer show errors here - they're handled at the higher level in conversation.py

    # Add marker if approve_all is active - we use this to communicate with the caller
    if use_approve_all:
        # Add a marker that the caller will check for
        approve_all_status = {
            "file_path": "__approve_all_status__",
            "success": True,
            "stdout": "Approve-all mode is active", 
            "stderr": "",
        }
        file_results.append(approve_all_status)

    return processed_response, file_results, has_error


def process_command_block(block_lines: List[str], commands: List[str]):
    """
    Process a block of shell commands, handling line continuations with backslashes.

    Distinguishes between:
    - Backslash as escape character (e.g., `echo \"hello\"`)
    - Backslash as line continuation marker

    Filters out any lines containing Q:COMMAND markers to prevent treating them as commands.

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

        # Skip empty lines or lines containing command markers
        if not line.strip():
            continue
        if "<Q:COMMAND" in line or "</Q:COMMAND>" in line:
            # Skip lines with command markers entirely
            continue

        if in_continuation:
            # This line is a continuation of the previous line
            current_command = current_command[:-1].rstrip() + " " + line.lstrip()
        else:
            # Not in continuation mode - if we have a stored command, add it
            if current_command and "<Q:COMMAND" not in current_command:
                commands.append(current_command)
            current_command = line

        # Check if this line ends with a continuation marker
        in_continuation = is_line_continuation(line)

        # If this is the last line or not a continuation, add the command
        is_last_line = i == len(block_lines) - 1
        if is_last_line and current_command and not in_continuation:
            # Only add if not a command marker
            if "<Q:COMMAND" not in current_command:
                commands.append(current_command)

    # Add any remaining command that wasn't added yet
    if (
        current_command
        and not in_continuation
        and current_command not in commands
        and "<Q:COMMAND" not in current_command
    ):
        commands.append(current_command)
