# q - Quick Claude CLI

A simple command-line tool for sending questions to Claude AI and getting beautifully formatted responses in your terminal.

**Author:** [mauro@sauco.net](mailto:mauro@sauco.net)

## Features

- 🌟 Interactive mode with conversation history
- 💻 Beautiful terminal formatting with syntax highlighting, code blocks, and more
- 📃 Markdown rendering for responses
- 🔐 Multiple API key sources (config file, environment variable, command-line)
- 📋 Context management via config file
- 💾 Load questions from file

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

### Install from PyPI (when published)

```bash
pip install q-claude
```

After installation, the `q` command will be available in your terminal.

## Configuration

Create a config file at `~/.config/q.conf` with the following format:

```
# Your Anthropic API key on the first non-comment line
sk-ant-api-key...

# Optional context section
#CONTEXT
Your context information here. This will be added to every query.
You can add multiple lines of context.
```

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
q --file questions.txt

# Use a different model
q --model claude-3-haiku-20240307 "What is the meaning of life?"

# Disable interactive mode
q --no-interactive "Tell me a joke"

# Disable context from config file
q --no-context

# Disable markdown formatting
q --no-md

# Add context from additional files
q --context-file data.txt --context-file notes.md
```

## Command-line Options

- `question`: The question to send to Claude
- `--file`, `-f`: Read question from file
- `--api-key`: Anthropic API key (defaults to config file or ANTHROPIC_API_KEY env var)
- `--model`: Model to use (default: claude-3-opus-20240229)
- `--no-interactive`: Disable interactive mode
- `--no-context`: Disable using context from config file
- `--no-md`: Disable markdown formatting of responses
- `--context-file`: Additional file to use as context (can be used multiple times)

## License

MIT
