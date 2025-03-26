"""Command execution functionality for q_cli."""

import os
import subprocess
import re
import difflib
import mimetypes
from typing import Tuple, List, Dict, Any, Optional
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table
from colorama import Fore, Style
from q_cli.utils.constants import DEBUG, MAX_FILE_DISPLAY_LENGTH

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
    # Debug output
    if DEBUG:
        console.print(f"[yellow]DEBUG: Executing command: {command}[/yellow]")

    # Check for dangerous commands
    if is_dangerous_command(command):
        if DEBUG:
            console.print(
                f"[yellow]DEBUG: Command blocked as dangerous: {command}[/yellow]"
            )
        return (-1, "", "This command has been blocked for security reasons.")

    # Check if this is a heredoc command
    heredoc_match = re.search(r'<<\s*[\'"]*([^\'"\s<]*)[\'"]*', command)
    if heredoc_match:
        if DEBUG:
            console.print(
                f"[yellow]DEBUG: Heredoc command detected: {command}[/yellow]"
            )
            console.print(
                "[yellow]Heredoc commands (with <<EOF) are not directly supported.[/yellow]"
            )
            console.print("[yellow]Use the file creation interface instead.[/yellow]")
        return (-1, "", "Heredoc commands are not supported for direct execution.")

    try:
        # Execute the command and capture output
        if DEBUG:
            console.print(f"[yellow]DEBUG: Starting subprocess for: {command}[/yellow]")
        process = subprocess.Popen(
            command,
            shell=True,
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

        if DEBUG:
            console.print(
                f"[yellow]DEBUG: Command completed with return code: {return_code}[/yellow]"
            )
            if stdout and len(stdout) > 0:
                console.print(
                    f"[yellow]DEBUG: Command stdout length: {len(stdout)} bytes[/yellow]"
                )
            if stderr and len(stderr) > 0:
                console.print(
                    f"[yellow]DEBUG: Command stderr length: {len(stderr)} bytes[/yellow]"
                )

        return (return_code, stdout, stderr)

    except subprocess.TimeoutExpired:
        if DEBUG:
            console.print(f"[yellow]DEBUG: Command timed out: {command}[/yellow]")
        return (-1, "", "Command timed out after 30 seconds")
    except Exception as e:
        if DEBUG:
            console.print(f"[yellow]DEBUG: Command error: {str(e)}[/yellow]")
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
        if DEBUG:
            console.print("\n[yellow]DEBUG: Q suggested a heredoc command:[/yellow]")
            console.print(f"[yellow]DEBUG: {command}[/yellow]")
            console.print(
                "[yellow]DEBUG: Heredoc commands cannot be executed directly.[/yellow]"
            )
            console.print(
                "[yellow]DEBUG: Use the 'cat > file' command followed by a separate content block instead.[/yellow]"
            )
        return False, False

    # Check if we need to ask for permission
    if permission_manager and not permission_manager.needs_permission(command):
        return True, False  # Command is pre-approved, no need to remember

    # If command is prohibited, don't even ask
    if permission_manager and permission_manager.is_command_prohibited(command):
        if DEBUG:
            console.print(
                f"[yellow]DEBUG: Command '{command}' is prohibited and cannot be executed.[/yellow]"
            )
        return False, False

    # Ask for user confirmation
    console.print("\n[bold yellow]Q wants to run this command:[/bold yellow]")
    console.print(f"[bold cyan]{command}[/bold cyan]")

    options = "[y/a/N] (y=yes, a=always, N=no): "
    response = input("\nExecute this command? " + options).lower().strip()

    if response.startswith("a"):
        # "Always" option - remember for the session
        return True, True

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
        if DEBUG:
            console.print(
                f"[yellow]DEBUG: Reading file from marker: {file_path}[/yellow]"
            )

        # Expand the file path (handle ~ and environment variables)
        expanded_path = os.path.expanduser(file_path)
        expanded_path = os.path.expandvars(expanded_path)

        if DEBUG:
            console.print(f"[yellow]DEBUG: Expanded path: {expanded_path}[/yellow]")

        # Make sure the path is relative to the current working directory if not absolute
        if not os.path.isabs(expanded_path):
            expanded_path = os.path.join(os.getcwd(), expanded_path)
            if DEBUG:
                console.print(f"[yellow]DEBUG: Absolute path: {expanded_path}[/yellow]")

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
            
            if DEBUG:
                console.print(f"[yellow]DEBUG: Magic detected type: {file_type}[/yellow]")
                console.print(f"[yellow]DEBUG: Magic detected MIME: {mime_type}[/yellow]")
            
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
            
            if DEBUG:
                console.print(f"[yellow]DEBUG: Magic not available, using extension-based detection[/yellow]")
                console.print(f"[yellow]DEBUG: Extension: {file_ext}, MIME: {mime_type}[/yellow]")
            
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
                
                # Use magic to detect if this is an image (ensure mime_type is not None)
                is_image = bool(mime_type and mime_type.startswith('image/'))
                
                # Fallback to extension check if magic doesn't identify it as an image
                if not is_image:
                    file_ext = os.path.splitext(expanded_path)[1].lower()
                    image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg']
                    is_image = file_ext in image_extensions
                
                if is_image:
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
                    
                    if DEBUG:
                        console.print(f"[yellow]DEBUG: UnicodeDecodeError but magic says: {file_type}[/yellow]")
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
        if DEBUG:
            console.print(f"[yellow]DEBUG: {error_msg}[/yellow]")
            import traceback
            console.print(f"[yellow]DEBUG: {traceback.format_exc()}[/yellow]")
        # Make sure this detailed error is returned so it can be sent to the model
        return False, "", error_msg, None, None


def write_file_from_marker(
    file_path: str, content: str, console: Console, auto_approve: bool = False
) -> Tuple[bool, str, str]:
    """
    Write content to a file based on a file writing marker.

    Args:
        file_path: Path where the file should be written
        content: Content to write to the file
        console: Console for output

    Returns:
        Tuple containing (success, stdout, stderr)
    """
    try:
        if DEBUG:
            console.print(
                f"[yellow]DEBUG: Writing file from marker: {file_path}[/yellow]"
            )
            console.print(
                f"[yellow]DEBUG: Content length: {len(content)} bytes[/yellow]"
            )

        # Expand the file path (handle ~ and environment variables)
        expanded_path = os.path.expanduser(file_path)
        expanded_path = os.path.expandvars(expanded_path)

        if DEBUG:
            console.print(f"[yellow]DEBUG: Expanded path: {expanded_path}[/yellow]")

        # Make sure the path is relative to the current working directory if not absolute
        if not os.path.isabs(expanded_path):
            expanded_path = os.path.join(os.getcwd(), expanded_path)
            if DEBUG:
                console.print(f"[yellow]DEBUG: Absolute path: {expanded_path}[/yellow]")

        # Ensure the directory exists
        directory = os.path.dirname(expanded_path)
        if directory and not os.path.exists(directory):
            if DEBUG:
                console.print(
                    f"[yellow]DEBUG: Creating directory: {directory}[/yellow]"
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
                if DEBUG:
                    console.print(
                        f"[yellow]DEBUG: Could not read existing file: {str(e)}[/yellow]"
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

        if DEBUG:
            console.print(
                f"[yellow]DEBUG: Content size after newline normalization: {len(content)} bytes[/yellow]"
            )

        # Show the file details to the user
        console.print("")  # Add spacing for better readability

        if is_overwrite:
            console.print(
                f"[bold yellow]Q wants to OVERWRITE an existing file:[/bold yellow] {expanded_path}"
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

            # Check if auto-approve is enabled
            if auto_approve:
                if DEBUG:
                    console.print(
                        f"[yellow]DEBUG: Auto-approving file operation for {expanded_path}[/yellow]"
                    )
                response = "y"  # Auto-approve
                console.print(
                    f"[bold green]Auto-approved:[/bold green] {'Overwriting' if is_overwrite else 'Creating'} file '{expanded_path}'"
                )
            else:
                # Ask for confirmation with appropriate message
                if is_overwrite:
                    prompt = f"\nOVERWRITE file '{expanded_path}' with the changes shown above? [y/n/r]: [y=yes, n=no, r=rename] "
                else:
                    prompt = f"\nCreate file '{expanded_path}' with this content? [y/n/r]: [y=yes, n=no, r=rename] "

                response = input(prompt).lower().strip()

                # Option to save with a different filename
                if response.startswith("r"):
                    new_filename = input("\nEnter new filename: ").strip()
                    if not new_filename:
                        error_msg = "File writing skipped - no filename provided"
                        if DEBUG:
                            console.print(f"[yellow]DEBUG: {error_msg}[/yellow]")
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
                        input(f"Proceed with writing to {expanded_path}? [y/N]: ")
                        .lower()
                        .strip()
                    )
                    if not confirm.startswith("y"):
                        error_msg = "File writing skipped by user"
                        if DEBUG:
                            console.print(f"[yellow]DEBUG: {error_msg}[/yellow]")
                        return False, "", error_msg
                elif not response.startswith("y"):
                    error_msg = "File writing skipped by user"
                    # Only show error details in debug mode
                    if DEBUG:
                        console.print(f"[yellow]DEBUG: {error_msg}[/yellow]")
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
        if DEBUG:
            console.print(
                f"[yellow]DEBUG: Writing content to file: {expanded_path}[/yellow]"
            )
            console.print(
                f"[yellow]DEBUG: Content length for writing: {len(content)} bytes[/yellow]"
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

                if DEBUG:
                    console.print(
                        f"[yellow]DEBUG: File written successfully via atomic operation[/yellow]"
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
        if DEBUG:
            console.print(
                f"[green]DEBUG: File write successful: {expanded_path}[/green]"
            )
        return True, f"File {action}: {expanded_path}", ""

    except Exception as e:
        error_msg = f"Error writing file: {str(e)}"
        # Only show error details in debug mode
        if DEBUG:
            console.print(f"[yellow]DEBUG: {error_msg}[/yellow]")
            import traceback

            console.print(f"[yellow]DEBUG: {traceback.format_exc()}[/yellow]")
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
    if DEBUG:
        console.print(
            "[yellow]DEBUG: Looking for file reading markers in response[/yellow]"
        )
    file_matches = extract_read_file_markers_from_response(response)

    if not file_matches:
        if DEBUG:
            console.print("[yellow]DEBUG: No file reading markers found[/yellow]")
        return response, [], False, []

    if DEBUG:
        console.print(
            f"[yellow]DEBUG: Found {len(file_matches)} file reading markers[/yellow]"
        )
        # Log details about each file marker
        for idx, (file_path, _) in enumerate(file_matches):
            console.print(
                f"[yellow]DEBUG: Marker {idx+1}: Path={file_path}[/yellow]"
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
        
        # Handle multimodal content (images, binary files)
        if success and binary_content and file_type in ["image", "binary"]:
            mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
            multimodal_result = {
                "file_path": file_path,
                "file_type": file_type,
                "content": binary_content,
                "mime_type": mime_type
            }
            multimodal_results.append(multimodal_result)
            
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
) -> Tuple[str, List[Dict[str, Any]], bool]:
    """
    Process a response from the model, handling any file writing markers.

    Args:
        response: The model's response text
        console: Console for output
        show_errors: Whether to display error messages to the user

    Returns:
        Tuple containing:
        - Processed response with file writing markers replaced
        - List of dictionaries with file writing results
        - Boolean indicating if any errors occurred
    """
    # Extract all file writing markers
    if DEBUG:
        console.print(
            "[yellow]DEBUG: Looking for file writing markers in response[/yellow]"
        )
    file_matches = extract_file_markers_from_response(response)

    if not file_matches:
        if DEBUG:
            console.print("[yellow]DEBUG: No file writing markers found[/yellow]")
        return response, [], False

    if DEBUG:
        console.print(
            f"[yellow]DEBUG: Found {len(file_matches)} file writing markers[/yellow]"
        )
        # Log details about each file marker
        for idx, (file_path, content, _) in enumerate(file_matches):
            console.print(
                f"[yellow]DEBUG: Marker {idx+1}: Path={file_path}, Content length={len(content)} bytes[/yellow]"
            )

    processed_response = response
    file_results = []
    has_error = False

    for file_path, content, original_marker in file_matches:
        success, stdout, stderr = write_file_from_marker(
            file_path, content, console, auto_approve
        )

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
