"""Command execution and permission configuration."""

from typing import List, Set

# Command execution special markers
SAVE_COMMAND_PREFIX = "/save"
RECOVER_COMMAND = "/recover"
TRANSPLANT_COMMAND = "/provider"

# Default always-approved commands (safe to run without confirmation)
DEFAULT_ALWAYS_APPROVED_COMMANDS: Set[str] = {
    "ls", "dir", "pwd", "cd", "echo", "cat", "less", "more", "head", "tail",
    "man", "which", "whatis", "clear", "date", "time", "whoami", "uname",
    "git status", "git log", "git diff", "git branch", "git remote", "git fetch",
    "python -V", "python --version", "pip list", "pip show", "pip freeze",
    "grep", "find", "top", "ps", "df", "du", "free", "ifconfig", "ip", "netstat",
    "printenv", "env"
}

# Default always-restricted commands (always require confirmation)
DEFAULT_ALWAYS_RESTRICTED_COMMANDS: Set[str] = {
    "rm", "rmdir", "mv", "cp", "chmod", "chown", "chgrp", "dd",
    "git add", "git reset", "git restore", "git checkout", "git pull", "git merge",
    "apt", "apt-get", "yum", "dnf", "brew", "nix", "pacman",
    "pip install", "pip uninstall",
    "npm install", "npm uninstall", "yarn add", "yarn remove",
}

# Default prohibited commands (never allowed to run)
DEFAULT_PROHIBITED_COMMANDS: Set[str] = {
    "sudo", "su", "shutdown", "reboot", "halt", "poweroff", "init", "mkfs",
    "curl", "wget", "nc", "telnet", "ssh",
    "^rm -rf /", "^rm -fr /", "^rm -rf --no-preserve-root"
}


def parse_command_list(command_list_str: str) -> List[str]:
    """Parse a JSON array string of commands into a list.
    
    Args:
        command_list_str: String containing commands in JSON array format
        
    Returns:
        List of individual commands
    """
    import json
    import logging
    
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