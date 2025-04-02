"""Constants used throughout the q_cli package."""

import os

# Environment variables
def get_debug():
    """Get DEBUG value from environment variables, ensuring it's current."""
    return os.environ.get("Q_DEBUG", "false").lower() in ["true", "1", "yes", "y", "on"]

# Note: This is a module-level constant that won't reflect changes to Q_DEBUG
# environment variable after module load. Use get_debug() to get current value.
DEBUG = get_debug()

# Model Constants - Removed general DEFAULT_MODEL

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
SENSITIVE_PATTERNS = [
    # API keys and tokens
    "sk-ant", "sk-", "api_key", "apikey", "token", "secret", "key", "pass", "pwd", "auth",
    # Service account patterns
    "private_key", "client_secret", "credentials", "account", "certificate",
    # Anthropic specific
    "anthropic\.api", "claude\.api",
    # OpenAI specific
    "openai\.api", "openai\.key", "gpt",
    # Vertex AI specific
    "vertex", "google_application", "gcp", "project_id",
    # Groq specific
    "groq\.api", "groq\.key",
    # General patterns
    "bearer", "authorization", "oauth"
]
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
    # File system destruction commands
    "rm -rf /", "rm -rf /*", "rm -rf .", "rm -fr /", "rm -fr /*",
    # Disk overwrite commands
    "> /dev/sda", "> /dev/hda", "dd if=/dev/zero", "mkfs", "format", 
    # Privilege escalation
    "sudo su", "sudo -i", "sudo su -", "su root", "sudo bash", "doas",
    # System modification (critical files/directories)
    "chmod -R 777 /", "chmod 777 -R /", "chmod +s /", "chown -R", 
    # Fork bombs and resource exhaustion
    ":(){:|:&};:", "while true;", ":(){ :|: & };:", "yes >",
    # Code execution from network
    "wget -O- | sh", "curl | sh", "curl | bash", "wget | bash", "fetch | sh", 
    "eval `curl", "eval `wget", "bash <(curl", "bash <(wget",
    # System control commands
    "shutdown", "reboot", "halt", "poweroff", "init 0", "init 6",
    # PATH_TRAVERSAL_ATTEMPT - special marker from extract_command_type
    "PATH_TRAVERSAL_ATTEMPT", 
    # Dangerous file targets
    ">/dev/sda", ">/dev/hda", ">/dev/sd", ">/dev/nvme", ">/proc/",
    # Intentional system crash attempts
    "kill -9 -1", "killall -9", ":(){ :", "echo > /proc/sys/kernel/panic",
    # Special regex patterns for command validation
    "^rm .*-[a-z]*f.*/$",
    "^sudo rm"
]
