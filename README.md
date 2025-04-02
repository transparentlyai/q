# q - The Command Line LLM Assistant

A simple command-line tool for sending questions to Q AI and getting beautifully formatted responses in your terminal. Now with support for multiple LLM providers via LiteLLM.

**Author:** [mauro@transparently.ai](mailto:mauro@transparently.ai)

## Features

- 🌟 Interactive mode with persistent conversation history
- 💻 Beautiful terminal formatting with syntax highlighting, code blocks, and more
- 📃 Markdown rendering for responses
- 🤖 Support for multiple LLM providers via LiteLLM (Anthropic, VertexAI, Groq, OpenAI)
- 🔐 Multiple API key sources (config file, environment variable, command-line)
- 📋 Context management via config file with environment variable support
- 💾 Load questions from file and save responses to file
- 🔄 History navigation with up/down arrow keys
- 🖱️ Terminal scrolling support for navigating long responses
- 🚪 Easy exit with Ctrl+C, Ctrl+D, or typing "exit"/"quit"
- 🖥️ Command execution - let Q run shell commands using special markers
- 🔒 Command permission system with session-based approvals
- 🌐 Web fetching - Q can access up-to-date information from the internet and analyze content for better responses

## Installation

### Install from GitHub

```bash
pip install git+https://github.com/transparentlyai/q.git
```

### Upgrade to the latest version

```bash
q --update
```
or if your version is too old

```bash
pip install --upgrade git+https://github.com/transparentlyai/q.git
```

## Configuration

The first time you run Q, it will automatically create a configuration file at `~/.config/q.conf` with sensible defaults. You don't need to manually create this file. The configuration includes:

- API key configuration (from environment variables)
- Default model settings
- Command permission settings
- Example context section

You can customize this file at any time to change Q's behavior. No need to restart Q - changes will be applied the next time you run a command.

For a complete example of all available configuration options, refer to the [example configuration file](https://github.com/transparentlyai/q/blob/main/q_cli/example_config.conf) in the repository.

### Supported Configuration Variables

#### Provider Configuration
- `PROVIDER`: LLM provider to use (supported: "anthropic", "vertexai", "groq", "openai")
- `ANTHROPIC_API_KEY`: Your Anthropic API key (for Claude models)
- `VERTEXAI_API_KEY`: Path to your VertexAI service account JSON file (for Gemini models)
- `VERTEXAI_PROJECT`: Your Google Cloud project ID (required for VertexAI)
- `VERTEXAI_LOCATION`: Your Google Cloud region (required for VertexAI, e.g., "us-central1")
- `GROQ_API_KEY`: Your Groq API key (for Llama and other models)
- `OPENAI_API_KEY`: Your OpenAI API key (for GPT models)
- `ANTHROPIC_MODEL`: Default model to use with Anthropic provider (e.g., "claude-3-7-sonnet-latest")
- `VERTEXAI_MODEL`: Default model to use with VertexAI provider (e.g., "gemini-2.0-flash-001")
- `GROQ_MODEL`: Default model to use with Groq provider (e.g., "deepseek-r1-distill-llama-70b")
- `OPENAI_MODEL`: Default model to use with OpenAI provider (e.g., "gpt-4o-mini")
- `ANTHROPIC_MAX_TOKENS`: Maximum output tokens for Anthropic provider (default: 8192)
- `VERTEXAI_MAX_TOKENS`: Maximum output tokens for VertexAI provider (default: 8192)
- `GROQ_MAX_TOKENS`: Maximum output tokens for Groq provider (default: 8192)
- `OPENAI_MAX_TOKENS`: Maximum output tokens for OpenAI provider (default: 8192)

Note: Each provider uses its own specific max tokens setting. There is no global setting.
- `ANTHROPIC_MAX_CONTEXT_TOKENS`: Maximum context tokens for Anthropic provider (default: 200000)
- `VERTEXAI_MAX_CONTEXT_TOKENS`: Maximum context tokens for VertexAI provider (default: 1000000)
- `GROQ_MAX_CONTEXT_TOKENS`: Maximum context tokens for Groq provider (default: 200000)
- `OPENAI_MAX_CONTEXT_TOKENS`: Maximum context tokens for OpenAI provider (default: 200000)
- `ANTHROPIC_MAX_TOKENS_PER_MIN`: Rate limit for Anthropic in tokens per minute (default: 80000)
- `VERTEXAI_MAX_TOKENS_PER_MIN`: Rate limit for VertexAI in tokens per minute (default: 80000)
- `GROQ_MAX_TOKENS_PER_MIN`: Rate limit for Groq in tokens per minute (default: 80000)
- `OPENAI_MAX_TOKENS_PER_MIN`: Rate limit for OpenAI in tokens per minute (default: 80000)

#### Command Permission Configuration
- `ALWAYS_APPROVED_COMMANDS`: List of commands that will always be executed without asking for permission (JSON array format)
- `ALWAYS_RESTRICTED_COMMANDS`: List of commands that will always require explicit permission (JSON array format)
- `PROHIBITED_COMMANDS`: List of commands that will never be executed (JSON array format)

See the [example configuration file](https://github.com/transparentlyai/q/blob/main/q_cli/example_config.conf) for recommended values.

**Note:** Command lists in your configuration file are added to the built-in defaults, not replacing them. This ensures core security features remain active while allowing you to customize permissions.

Environment variables in the config file are expanded using the syntax `$VAR` or `${VAR}`.

#### Provider-Specific Information

> **Important Note for VertexAI Users:** VertexAI requires **three** configuration settings to work properly:
> 1. A service account JSON file path (set as `VERTEXAI_API_KEY`)
> 2. A Google Cloud project ID (set as `VERTEXAI_PROJECT`)
> 3. A region/location (set as `VERTEXAI_LOCATION`)
> 
> Missing any of these will result in authentication errors.

##### Recommended Models by Provider:
- **Anthropic**: `claude-3-7-sonnet-latest` (default), `claude-3-haiku-latest`, `claude-3-opus-latest`
  - Check the available Claude models here: https://docs.anthropic.com/en/docs/about-claude/models/all-models
- **VertexAI**: `gemini-2.0-flash-001` (default), `gemini-1.5-pro`, `gemini-1.5-flash`
  - Check available Gemini models here: https://cloud.google.com/vertex-ai/docs/generative-ai/learn/models
- **Groq**: `deepseek-r1-distill-llama-70b` (default), `llama3-70b-8192`, `llama3-8b-8192`, `mixtral-8x7b-32768`
  - Check Groq's model lineup here: https://console.groq.com/docs/models
- **OpenAI**: `gpt-4o-mini` (default), `gpt-4o`, `gpt-4-turbo`, `gpt-3.5-turbo`
  - Check OpenAI models here: https://platform.openai.com/docs/models

##### Context Windows by Provider:
- **Anthropic Claude**: 200K tokens (Claude 3 models)
- **VertexAI Gemini**: 1M tokens (Gemini 1.5 and 2.0 models)
- **Groq models**: Varies by model (8K-32K tokens)
- **OpenAI models**: Varies by model (8K-128K tokens)

##### Authentication Requirements:
- **Anthropic**: API key only
- **VertexAI**: 
  - Service account JSON file (specified in `VERTEXAI_API_KEY`)
  - Project ID (required, specified in `VERTEXAI_PROJECT`)
  - Location (required, specified in `VERTEXAI_LOCATION`)
- **Groq**: API key only
- **OpenAI**: API key only

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
q -m claude-3-haiku-latest "What is the meaning of life?"

# Use a different provider
q --provider vertexai "What is the meaning of life?" 

# Specify provider and model
q --provider groq -m llama3-70b-8192 "What is the meaning of life?"

# Use OpenAI provider
q --provider openai -m gpt-4o "What is the meaning of life?"

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

# Provider-specific examples
# VertexAI with service account
q --provider vertexai --api-key /path/to/service-account.json \
  --env VERTEXAI_PROJECT=my-gcp-project --env VERTEXAI_LOCATION=us-central1 \
  "Tell me about Google Cloud"
```

### Using Environment Variables for Authentication

You can also set environment variables directly to authenticate with different providers:

```bash
# Anthropic
export ANTHROPIC_API_KEY=your_api_key
q --provider anthropic "Your question here"

# VertexAI 
export VERTEXAI_API_KEY=/path/to/service-account.json
export VERTEXAI_PROJECT=your-gcp-project-id
export VERTEXAI_LOCATION=us-central1
q --provider vertexai "Your question here"

# Groq
export GROQ_API_KEY=your_api_key
q --provider groq "Your question here"

# OpenAI
export OPENAI_API_KEY=your_api_key
q --provider openai "Your question here"
```

## Interactive Mode Features

In interactive mode, you can:

- Navigate through command history with the up/down arrow keys
- Use Tab for auto-completion of slash commands (`/save`, `/transplant`) and file paths
- Exit by typing `exit` or `quit`, or by pressing Ctrl+C or Ctrl+D
- Save the last Q response to a file by typing `/save` followed by a path:
  ```
  > /save ~/responses/answer.md
  ```
- Change LLM provider and model during a conversation by typing `/transplant`:
  ```
  > /transplant
  ```
  This will show you a list of currently configured providers, allow you to select a provider, 
  and optionally specify a model. The conversation will continue with the new provider/model.
  Your choice will be saved to the config file (~/.config/q.conf) as the new default provider.
  A timestamped backup of your config file is automatically created before any changes.
- Q can suggest and run shell commands to solve your problems:
  - Each command is presented individually for your approval
  - Commands are categorized as approved, restricted, or prohibited
  - You'll be asked to confirm before executing any command that needs permission
- Q can fetch content from the web to provide up-to-date information in two ways:
  - Displaying web content directly to you with URL markers
  - Fetching web content as context for Q to analyze and use in responses
- Q can create files for you automatically using the write command:
  - Format: `<Q:COMMAND type="write" path="path/to/file">content</Q:COMMAND>`
  - You'll be asked to confirm before any file is written
  - The file will be shown to you for review before creating it
  - This approach is preferred over using shell commands for file creation
- Q runs shell commands using the shell command:
  - Format: `<Q:COMMAND type="shell">command</Q:COMMAND>`
  - You'll be asked to confirm before any command is executed
  - Multi-line commands can be included inside the markers
- Use the `--no-empty` flag to disable sending empty inputs (pressing Enter without typing anything)
- Use the `--no-execute` flag to disable command execution functionality
- Use the `--no-web` flag to disable web content fetching
- Use the `--no-file-write` flag to disable file writing functionality
- For maximum security, you can use all three flags: `--no-execute --no-web --no-file-write`

### Command Permission System

Q includes a sophisticated command permission system that balances security with convenience:

- **Command Categories**: Commands are classified into three categories:
  - **Approved Commands**: Automatically executed without asking for permission
  - **Restricted Commands**: Always require explicit permission before execution
  - **Prohibited Commands**: Never allowed to execute, regardless of user input

- **Permission Hierarchy**: When determining if a command needs permission, Q follows this priority order:
  1. If the command is prohibited → Never execute (highest priority)
  2. If the command is restricted → Always require permission
  3. If the command was previously approved in this session → Auto-approve
  4. If the command is in the approved list → Auto-approve
  5. By default, ask for permission (lowest priority)

- **Default + Configuration**: The command permissions combine both built-in defaults and your configuration:
  - Default commands are always included for security and functionality
  - Commands in your config file are added to these defaults, not replacing them
  - You can add your frequently used commands to the approved list in your config

- **Session-Based Approvals**: When you approve a command once, Q remembers it for the current session

- **Approval Options**: When prompted about executing a command, you can:
  - `y` or `yes`: Execute this one time
  - `a` or `always`: Always execute this command type in the current session
  - `n` or `no`: Don't execute this command

- **Command Pattern Matching**: Commands are matched against patterns, not just exact matches

- **Security First**: Potentially dangerous commands require explicit permission

### Default Permissions

Q comes with the following default command permissions:

#### Default Approved Commands (auto-approved)
- `ls` - List directory contents
- `pwd` - Print working directory
- `echo` - Display a line of text
- `date` - Display or set date and time
- `whoami` - Print current user
- `uptime` - System uptime
- `uname` - Print system information
- `hostname` - Print system name
- `cat` - Concatenate and display files
- `find` - Search for files
- `sed` - Stream editor for filtering/transforming text
- `chmod` - Change file permissions
- `chown` - Change file owner
- `chgrp` - Change group ownership
- `ps` - Report process status
- `env` - Display environment
- `printenv` - Print environment variables
- `export` - Set environment variables
- `cd` - Change directory
- `dirs` - Display directory stack
- `realpath` - Print resolved path
- `touch` - Change file timestamps
- `mkdir` - Create directories
- `cp` - Copy files
- `mv` - Move files
- `head` - Output first part of files
- `tail` - Output last part of files
- `wc` - Print line, word, and byte counts
- `sort` - Sort lines of text files
- `uniq` - Report or filter out repeated lines
- `cut` - Remove sections from lines
- `join` - Join lines on a common field
- `comm` - Compare sorted files
- `diff` - Compare files
- `df` - Report file system disk space usage
- `du` - Estimate file space usage
- `git` - Version control system

#### Default Restricted Commands (require permission)
- `sudo` - Execute command as another user
- `su` - Change user ID or become superuser
- `chmod` - Change file permissions
- `chown` - Change file owner
- `mkfs` - Build a Linux filesystem
- `dd` - Convert and copy a file
- `systemctl` - Control systemd system
- `rm` - Remove files or directories
- `mv` - Move/rename files
- `cp` - Copy files
- `apt` - Package management
- `yum` - Package management
- `dnf` - Package management
- `pacman` - Package management
- `brew` - Package management
- `npm` - Node.js package management
- `pip` - Python package management

#### Default Prohibited Commands (never allowed)
- `rm -rf /` - Delete entire filesystem
- `rm -rf /*` - Delete all files in root
- `mkfs` - Create filesystem (can erase disk)
- `> /dev/sda` - Erase disk
- `dd if=/dev/zero` - Zero out device
- `:(){:|:&};:` - Fork bomb
- `chmod -R 777 /` - Give everyone full permissions to all files
- `wget -O- | sh` - Download and execute script
- `curl | sh` - Download and execute script
- `eval \`curl\`` - Download and execute script
- `shutdown` - Shut down system
- `reboot` - Restart system
- `halt` - Stop system

You can add your own commands to any of these categories in your configuration file.

## Command-line Options

- `question`: The question to send to Q
- `--file`, `-f`: Read question from file
- `--api-key`, `-k`: API key for the selected provider
- `--model`, `-m`: Model to use (defaults to provider-specific default)
- `--provider`: LLM provider to use ("anthropic", "vertexai", "groq")
- `--no-interactive`, `-i`: Disable interactive mode
- `--no-context`, `-c`: Disable using context from config file
- `--no-md`, `-p`: Disable markdown formatting of responses
- `--context-file`, `-x`: Additional file to use as context (can be used multiple times)
- `--confirm-context`, `-w`: Show context and ask for confirmation before sending to Q
- `--no-empty`, `-e`: Disable sending empty inputs in interactive mode
- `--no-execute`: Disable command execution functionality 
- `--no-web`: Disable web content fetching functionality
- `--no-file-write`: Disable file writing functionality 
- `--no-command-approval`: Disable command approval system (not recommended)
- `--version`, `-v`: Show program version and exit
- `--interactive`: Force interactive mode without a question                                                                                                   
- `--file-tree`: Include file tree of current directory in context                                                                                             
- `--max-context-tokens`: Maximum tokens for context (default: 200000)                                                                                         
- `--context-priority-mode`: Context priority mode (balanced, code, conversation)                                                                              
- `--context-stats`: Show context statistics before sending to model                                                                                           
- `--update`: Update q to the latest version and exit                                                                                                          
- `--dry-run`: Print the full message that would be sent to the model and exit  

