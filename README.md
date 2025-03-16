# q - Quick Claude CLI

A simple command-line tool for sending questions to Claude AI and getting beautifully formatted responses in your terminal.

**Author:** [mauro@sauco.net](mailto:mauro@sauco.net)

## Features

- 🌟 Interactive mode with persistent conversation history
- 💻 Beautiful terminal formatting with syntax highlighting, code blocks, and more
- 📃 Markdown rendering for responses
- 🔐 Multiple API key sources (config file, environment variable, command-line)
- 📋 Context management via config file with environment variable support
- 💾 Load questions from file
- 🔄 History navigation with up/down arrow keys
- 🖱️ Terminal scrolling support for navigating long responses
- 🚪 Easy exit with Ctrl+C, Ctrl+D, or typing "exit"/"quit"

## Installation

### Install directly from GitHub

```bash
pip install git+https://github.com/transparentlyai/q.git
```

### Install from local repository

```bash
# Clone the repository
git clone https://github.com/transparentlyai/q.git
cd q

# Install the package (will install the 'q' command)
pip install -e .
```

## Configuration

Create a config file at `~/.config/q.conf` with the following format:

```
# Configuration variables (in KEY=value format)
# Environment variables can be used with $VAR or ${VAR} syntax
ANTHROPIC_API_KEY=${CLAUDE_API_KEY}
MODEL=claude-3-7-sonnet-latest
MAX_TOKENS=4000
# Example of using environment variable: DATA_DIR=$HOME/data

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

Environment variables in the config file are expanded using the syntax `$VAR` or `${VAR}`.

check the anthropic available models here: https://docs.anthropic.com/en/docs/about-claude/models/all-models

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

# Check the version
q -v
```

## Command-line Options

- `question`: The question to send to Claude
- `--file`, `-f`: Read question from file
- `--api-key`, `-k`: Anthropic API key (defaults to config file or ANTHROPIC_API_KEY env var)
- `--model`, `-m`: Model to use (default: claude-3.7-latest)
- `--no-interactive`, `-i`: Disable interactive mode
- `--no-context`, `-c`: Disable using context from config file
- `--no-md`, `-p`: Disable markdown formatting of responses
- `--context-file`, `-x`: Additional file to use as context (can be used multiple times)
- `--confirm-context`, `-w`: Show context and ask for confirmation before sending to Claude
- `--version`, `-v`: Show program version and exit

## License

MIT
