# q - The Command Line Assistant

A simple command-line tool for sending questions to Q AI and getting beautifully formatted responses in your terminal.

**Author:** [mauro@transparently.ai](mailto:mauro@transparently.ai)

## Features

- 🌟 Interactive mode with persistent conversation history
- 💻 Beautiful terminal formatting with syntax highlighting, code blocks, and more
- 📃 Markdown rendering for responses
- 🔐 Multiple API key sources (config file, environment variable, command-line)
- 📋 Context management via config file with environment variable support
- 💾 Load questions from file and save responses to file
- 🔄 History navigation with up/down arrow keys
- 🖱️ Terminal scrolling support for navigating long responses
- 🚪 Easy exit with Ctrl+C, Ctrl+D, or typing "exit"/"quit"
- 🖥️ Command execution mode - let Q suggest and run shell commands
- 🔒 Command permission system with session-based approvals

## Installation

### Install from GitHub

```bash
pip install git+https://github.com/transparentlyai/q.git
```

### Upgrade to the latest version

```bash
pip install --upgrade git+https://github.com/transparentlyai/q.git
```

## Configuration

Create a config file at `~/.config/q.conf` with the following format:

```
# Configuration variables (in KEY=value format)
# Environment variables can be used with $VAR or ${VAR} syntax
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
MODEL=claude-3.7-latest
MAX_TOKENS=4096

# Command permission settings
# These can be specified in JSON array format (recommended) or comma-separated list
# JSON format handles special characters and spaces better
ALWAYS_APPROVED_COMMANDS=[
    "ls", "pwd", "echo", "date", "whoami", "uptime", "uname", "hostname"
]

# These commands always require explicit permission
ALWAYS_RESTRICTED_COMMANDS=[
    "sudo", "su", "chmod", "chown", "mkfs", "dd", "systemctl", "rm", 
    "mv", "cp", "apt", "yum", "dnf", "pacman", "brew", "npm", "pip"
]

# These commands can never be executed
PROHIBITED_COMMANDS=[
    "rm -rf /", "rm -rf /*", "mkfs", "> /dev/sda", "dd if=/dev/zero", 
    ":(){:|:&};:", "chmod -R 777 /", "wget -O- | sh", "curl | sh", 
    "eval `curl`", "shutdown", "reboot", "halt"
]

# Optional context section - everything after #CONTEXT is sent with every query
# Environment variables are also expanded in the context section
#CONTEXT
- my name is Mauro
- The environment is Linux nixos
- be brief unless asked otherwise
- My home directory is $HOME
```

An example configuration file is provided in the repository as `example_config.conf`.

### Supported Configuration Variables

- `ANTHROPIC_API_KEY`: Your Anthropic API key (should start with `sk-ant-api-`)
- `MODEL`: Default model to use (e.g., "claude-3-opus-20240229", "claude-3-haiku-20240307")
- `MAX_TOKENS`: Maximum number of tokens in the response (default: 4096)
- `ALWAYS_APPROVED_COMMANDS`: List of commands that will always be executed without asking for permission (JSON array format recommended)
- `ALWAYS_RESTRICTED_COMMANDS`: List of commands that will always require explicit permission (JSON array format recommended)
- `PROHIBITED_COMMANDS`: List of commands that will never be executed (JSON array format recommended)

Environment variables in the config file are expanded using the syntax `$VAR` or `${VAR}`.

Check the anthropic available models here: https://docs.anthropic.com/en/docs/about-claude/models/all-models

⚠️ **Security Warning:** 
- Never include API keys or sensitive information in your context section or context files
- Any text that looks like an API key, or contains words like "api_key", "key", "token", or "secret" will be automatically redacted
- The tool includes safeguards to prevent accidentally sending API keys in context, but use caution with sensitive information

## Usage

```bash
# Interactive mode (default)
q

# Single question
q "What is the capital of France?"

# From file
q -f questions.txt

# Use a different model
q -m claude-3-haiku-20240307 "What is the meaning of life?"

# Disable interactive mode
q -i "Tell me a joke"

# Disable context from config file
q -c

# Disable markdown formatting
q -p

# Add context from additional files
q -x data.txt -x notes.md

# Disable sending empty inputs in interactive mode
q -e

# Check the version
q -v
```

## Interactive Mode Features

In interactive mode, you can:

- Navigate through command history with the up/down arrow keys
- Exit by typing `exit` or `quit`, or by pressing Ctrl+C or Ctrl+D
- Save the last Q response to a file by typing `save` followed by a path:
  ```
  > save ~/responses/answer.md
  ```
- Q can suggest shell commands that might help with your question. When it does, you'll be asked to confirm before any command is executed
- Use the `--no-empty` flag to disable sending empty inputs (pressing Enter without typing anything)
- Use the `--no-execute` flag to disable command execution functionality

### Command Permission System

Q includes a sophisticated command permission system:

- **Command Categories**: Commands can be categorized as approved, restricted, or prohibited in your config file
- **Session-Based Approvals**: When you approve a command once, Q remembers it for the current session
- **Approval Options**: When prompted about executing a command, you can:
  - `y` or `yes`: Execute this one time
  - `a` or `always`: Always execute this command type in the current session
  - `n` or `no`: Don't execute this command
- **Command Pattern Matching**: Commands are matched against patterns, not just exact matches
- **Security First**: Potentially dangerous commands require explicit permission

## Command-line Options

- `question`: The question to send to Q
- `--file`, `-f`: Read question from file
- `--api-key`, `-k`: Anthropic API key (defaults to config file or ANTHROPIC_API_KEY env var)
- `--model`, `-m`: Model to use (default: claude-3.7-latest)
- `--no-interactive`, `-i`: Disable interactive mode
- `--no-context`, `-c`: Disable using context from config file
- `--no-md`, `-p`: Disable markdown formatting of responses
- `--context-file`, `-x`: Additional file to use as context (can be used multiple times)
- `--confirm-context`, `-w`: Show context and ask for confirmation before sending to Q
- `--no-empty`, `-e`: Disable sending empty inputs in interactive mode
- `--no-execute`: Disable command execution functionality
- `--no-command-approval`: Disable command approval system (not recommended)
- `--version`, `-v`: Show program version and exit

## Development

If you want to contribute to Q, here's how to get started:

1. Clone the repository and install it in development mode:
   ```bash
   git clone https://github.com/transparentlyai/q.git
   cd q
   pip install -e .
   ```

2. Run linting and type checking:
   ```bash
   flake8 q_cli
   black q_cli
   mypy q_cli
   ```

3. Testing (run after implementing changes):
   ```bash
   python -m unittest discover -s tests
   ```

## License

MIT
