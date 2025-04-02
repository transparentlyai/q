"""Constants used throughout the q_cli package."""

import os

# Import constants from config modules
from q_cli.config.context import (
    get_debug,
    DEFAULT_MAX_CONTEXT_TOKENS,
    DEFAULT_CONTEXT_PRIORITY_MODE,
    ESSENTIAL_PRIORITY,
    IMPORTANT_PRIORITY,
    SUPPLEMENTARY_PRIORITY,
    ESSENTIAL_TOKEN_ALLOCATION,
    IMPORTANT_TOKEN_ALLOCATION,
    SUPPLEMENTARY_TOKEN_ALLOCATION,
    INCLUDE_FILE_TREE,
    MAX_HISTORY_TURNS,
    HISTORY_PATH
)

from q_cli.config.providers import (
    DEFAULT_PROVIDER,
    SUPPORTED_PROVIDERS,
    ANTHROPIC_DEFAULT_MODEL,
    VERTEXAI_DEFAULT_MODEL,
    GROQ_DEFAULT_MODEL,
    OPENAI_DEFAULT_MODEL,
    ANTHROPIC_MAX_TOKENS,
    VERTEXAI_MAX_TOKENS,
    GROQ_MAX_TOKENS,
    OPENAI_MAX_TOKENS,
    ANTHROPIC_MAX_CONTEXT_TOKENS,
    VERTEXAI_MAX_CONTEXT_TOKENS,
    GROQ_MAX_CONTEXT_TOKENS,
    OPENAI_MAX_CONTEXT_TOKENS,
    ANTHROPIC_MAX_TOKENS_PER_MIN,
    VERTEXAI_MAX_TOKENS_PER_MIN,
    GROQ_MAX_TOKENS_PER_MIN,
    OPENAI_MAX_TOKENS_PER_MIN,
    RATE_LIMIT_COOLDOWN
)

from q_cli.config.commands import (
    SAVE_COMMAND_PREFIX,
    RECOVER_COMMAND,
    TRANSPLANT_COMMAND,
    DEFAULT_ALWAYS_APPROVED_COMMANDS,
    DEFAULT_ALWAYS_RESTRICTED_COMMANDS,
    DEFAULT_PROHIBITED_COMMANDS
)

# Note: This is a module-level constant that won't reflect changes to Q_DEBUG
# environment variable after module load. Use get_debug() to get current value.
DEBUG = get_debug()

# File Paths
CONFIG_PATH = os.path.expanduser("~/.config/q.conf")
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
MAX_FILE_TREE_ENTRIES = 100  # Maximum number of entries to include in file tree

# Prompts directory
PROMPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "prompts",
)

# Commands
EXIT_COMMANDS = ["exit", "quit", "q"]