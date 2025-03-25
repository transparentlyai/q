"""Constants used throughout the q_cli package."""

import os

# Environment variables
DEBUG = os.environ.get("Q_DEBUG", "false").lower() == "true"

# Model Constants
# Keep model name as is for API compatibility
DEFAULT_MODEL = "claude-3-7-sonnet-latest"
DEFAULT_MAX_TOKENS = 4096
RESPONSE_TIMEOUT_SECONDS = 30  # Timeout for waiting on Claude's response

# File Paths
CONFIG_PATH = os.path.expanduser("~/.config/q.conf")
HISTORY_PATH = os.path.expanduser("~/.qhistory")

# Security
SENSITIVE_PATTERNS = ["sk-ant", "api_key", "apikey", "token", "secret", "key"]
REDACTED_TEXT = "[REDACTED - Potential sensitive information]"

# Display options
MAX_FILE_DISPLAY_LENGTH = 500  # Characters to show when previewing file content
INCLUDE_FILE_TREE = False  # Include file tree of the current directory in context
MAX_FILE_TREE_ENTRIES = 100  # Maximum number of entries to include in file tree

# Context Management
DEFAULT_MAX_CONTEXT_TOKENS = 200000  # Default maximum tokens for context
DEFAULT_CONTEXT_PRIORITY_MODE = "balanced"  # Default context priority mode (balanced, code, conversation)

# Context Prioritization
ESSENTIAL_PRIORITY = "essential"  # Highest priority context (system prompt, recent msgs)
IMPORTANT_PRIORITY = "important"  # Important context (file structure, key files)
SUPPLEMENTARY_PRIORITY = "supplementary"  # Lower priority context (can be trimmed)

# Token Allocation (percentage of total context budget)
ESSENTIAL_TOKEN_ALLOCATION = 0.30  # 30% for essential context
IMPORTANT_TOKEN_ALLOCATION = 0.40  # 40% for important context
SUPPLEMENTARY_TOKEN_ALLOCATION = 0.30  # 30% for supplementary context

# Prompts directory
PROMPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets",
)

# Commands
EXIT_COMMANDS = ["exit", "quit", "q"]
SAVE_COMMAND_PREFIX = "save "

# Default permission-related values in JSON format

DEFAULT_ALWAYS_APPROVED_COMMANDS: list[str] = [
    "ls",
    "pwd",
    "echo",
    "date",
    "whoami",
    "uptime",
    "uname",
    "hostname",
    "cat",
    "find",
    "sed",
    "chmod",
    "chown",
    "chgrp",
    "ps",
    "env",
    "printenv",
    "export",
    "cd",
    "dirs",
    "realpath",
    "touch",
    "mkdir",
    "cp",
    "mv",
    "head",
    "tail",
    "wc",
    "sort",
    "uniq",
    "cut",
    "join",
    "comm",
    "diff",
    "df",
    "du",
    "git",
]

DEFAULT_ALWAYS_RESTRICTED_COMMANDS: list[str] = [
    "sudo",
    "su",
    "mkfs",
    "dd",
    "systemctl",
    "rm",
    "apt",
    "yum",
    "dnf",
    "pacman",
    "brew",
    "npm",
    "pip",
]

DEFAULT_PROHIBITED_COMMANDS: list[str] = [
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "> /dev/sda",
    "dd if=/dev/zero",
    ":(){:|:&};:",
    "chmod -R 777 /",
    "wget -O- | sh",
    "curl | sh",
    "eval `curl`",
    "shutdown",
    "reboot",
    "halt",
]
