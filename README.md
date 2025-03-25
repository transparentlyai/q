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

- `ANTHROPIC_API_KEY`: Your Anthropic API key (should start with `sk-ant-api-`)
- `MODEL`: Default model to use (e.g., "claude-3-opus-20240229", "claude-3-haiku-20240307")
- `MAX_TOKENS`: Maximum number of tokens in the response (default: 4096)
- `ALWAYS_APPROVED_COMMANDS`: List of commands that will always be executed without asking for permission (JSON array format)
- `ALWAYS_RESTRICTED_COMMANDS`: List of commands that will always require explicit permission (JSON array format)
- `PROHIBITED_COMMANDS`: List of commands that will never be executed (JSON array format)

See the [example configuration file](https://github.com/transparentlyai/q/blob/main/q_cli/example_config.conf) for recommended values.

**Note:** Command lists in your configuration file are added to the built-in defaults, not replacing them. This ensures core security features remain active while allowing you to customize permissions.

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
- Q can suggest and run shell commands to solve your problems:
  - Each command is presented individually for your approval
  - Commands are categorized as approved, restricted, or prohibited
  - You'll be asked to confirm before executing any command that needs permission
- Q can fetch content from the web to provide up-to-date information in two ways:
  - Displaying web content directly to you with URL markers
  - Fetching web content as context for Q to analyze and use in responses
- Q can create files for you automatically using the WRITE_FILE mechanism:
  - Format: `<<WRITE_FILE:path/to/file>>content<<WRITE_FILE>>`
  - You'll be asked to confirm before any file is written
  - The file will be shown to you for review before creating it
  - This approach is preferred over using shell commands for file creation
- Q runs shell commands using the RUN_SHELL mechanism:
  - Format: `<<RUN_SHELL>>command<<RUN_SHELL>>`
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
- `--api-key`, `-k`: Anthropic API key (defaults to config file or ANTHROPIC_API_KEY env var)
- `--model`, `-m`: Model to use (default: claude-3.7-latest)
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


