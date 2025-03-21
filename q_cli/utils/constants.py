"""Constants used throughout the q_cli package."""

import os

# Version - moved to __init__.py

# Model Constants
DEFAULT_MODEL = "claude-3.7-latest"  # Keep model name as is for API compatibility
DEFAULT_MAX_TOKENS = 4096

# File Paths
CONFIG_PATH = os.path.expanduser("~/.config/q.conf")
HISTORY_PATH = os.path.expanduser("~/.qhistory")

# Security
SENSITIVE_PATTERNS = ["sk-ant", "api_key", "apikey", "token", "secret", "key"]
REDACTED_TEXT = "[REDACTED - Potential sensitive information]"

# Commands
EXIT_COMMANDS = ["exit", "quit"]
SAVE_COMMAND_PREFIX = "save "

# Default permission-related values
DEFAULT_ALWAYS_APPROVED_COMMANDS = [
    "ls", "pwd", "echo", "date", "whoami", "uptime", "uname", "hostname", 
]

DEFAULT_ALWAYS_RESTRICTED_COMMANDS = [
    "sudo", "su", "chmod", "chown", "mkfs", "dd", "systemctl", "rm", 
    "mv", "cp", "apt", "yum", "dnf", "pacman", "brew", "npm", "pip"
]

DEFAULT_PROHIBITED_COMMANDS = [
    "rm -rf /", "rm -rf /*", "mkfs", "> /dev/sda", "dd if=/dev/zero", 
    ":(){:|:&};:", "chmod -R 777 /", "wget -O- | sh", "curl | sh", 
    "eval `curl", "shutdown", "reboot", "halt"
]
