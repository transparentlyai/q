"""Constants used throughout the q_cli package."""

import os

# Environment variables
DEBUG = os.environ.get("Q_DEBUG", "false").lower() in ["true", "1", "yes", "y", "on"]

# Model Constants
# Keep model name as is for API compatibility
DEFAULT_MODEL = "claude-3-7-sonnet-latest"

# LLM Provider Constants
DEFAULT_PROVIDER = "anthropic"
SUPPORTED_PROVIDERS = ["anthropic", "vertexai", "groq", "openai"]

# Provider-specific model defaults
ANTHROPIC_DEFAULT_MODEL = "claude-3-7-sonnet-latest"
VERTEXAI_DEFAULT_MODEL = "gemini-2.0-flash-001"
GROQ_DEFAULT_MODEL = "deepseek-r1-distill-llama-70b"
OPENAI_DEFAULT_MODEL = "gpt-4o-mini"

# Provider-specific max token defaults
ANTHROPIC_MAX_TOKENS = 8192
VERTEXAI_MAX_TOKENS = 65535
GROQ_MAX_TOKENS = 8192
OPENAI_MAX_TOKENS = 8192

# Provider-specific context token limits
ANTHROPIC_MAX_CONTEXT_TOKENS = 200000
VERTEXAI_MAX_CONTEXT_TOKENS = 1000000
GROQ_MAX_CONTEXT_TOKENS = 200000
OPENAI_MAX_CONTEXT_TOKENS = 200000

# Rate limiting - provider specific
ANTHROPIC_MAX_TOKENS_PER_MIN = 80000
VERTEXAI_MAX_TOKENS_PER_MIN = 80000
GROQ_MAX_TOKENS_PER_MIN = 80000
OPENAI_MAX_TOKENS_PER_MIN = 80000
RATE_LIMIT_COOLDOWN = 60  # Seconds to wait after hitting rate limit

# File Paths
CONFIG_PATH = os.path.expanduser("~/.config/q.conf")
HISTORY_PATH = os.path.expanduser("~/.qhistory")
SESSION_PATH = os.path.expanduser("~/.qsession")

# Security
SENSITIVE_PATTERNS = ["sk-ant", "api_key", "apikey", "token", "secret", "key"]
REDACTED_TEXT = "[REDACTED - Potential sensitive information]"

# Display options
MAX_FILE_DISPLAY_LENGTH = 500  # Characters to show when previewing file content
INCLUDE_FILE_TREE = False  # Include file tree of the current directory in context
MAX_FILE_TREE_ENTRIES = 100  # Maximum number of entries to include in file tree

# Context Management
DEFAULT_MAX_CONTEXT_TOKENS = 200000  # Default maximum tokens for context
DEFAULT_CONTEXT_PRIORITY_MODE = (
    "balanced"  # Default context priority mode (balanced, code, conversation)
)

# Context Prioritization
ESSENTIAL_PRIORITY = (
    "essential"  # Highest priority context (system prompt, recent msgs)
)
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
SAVE_COMMAND_PREFIX = "/save "
RECOVER_COMMAND = "/recover"
MAX_HISTORY_TURNS = 5  # Maximum number of conversation turns to keep in history

# Default permission-related values in JSON format

DEFAULT_ALWAYS_APPROVED_COMMANDS: list[str] = [
    "alias",
    "apropos",
    "arp",
    "awk",
    "cal",
    "cat",
    "cd",
    "chgrp",
    "chmod",
    "chown",
    "comm",
    "cp",
    "cut",
    "date",
    "df",
    "diff",
    "dig",
    "dirs",
    "du",
    "echo",
    "egrep",
    "env",
    "export",
    "fgrep",
    "file",
    "find",
    "free",
    "git",
    "grep",
    "head",
    "history",
    "host",
    "hostname",
    "ifconfig",
    "ip",
    "join",
    "locate",
    "ls",
    "lsblk",
    "lsof",
    "lspci",
    "lsusb",
    "man",
    "mkdir",
    "mount",
    "mv",
    "netstat",
    "nslookup",
    "pgrep",
    "ping",
    "printenv",
    "ps",
    "pwd",
    "q",
    "realpath",
    "route",
    "sed",
    "sort",
    "ss",
    "stat",
    "tail",
    "test",
    "touch",
    "traceroute",
    "tty",
    "type",
    "uname",
    "uniq",
    "uptime",
    "w",
    "wc",
    "whatis",
    "whereis",
    "which",
    "who",
    "whoami",
    "xargs"
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
