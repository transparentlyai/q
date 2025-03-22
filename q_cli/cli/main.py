"""Main entry point for the q_cli package."""

import anthropic
import os
import sys

from q_cli.cli.args import setup_argparse
from q_cli.io.config import read_config_file, build_context
from q_cli.io.input import create_prompt_session, get_initial_question, confirm_context
from q_cli.io.output import setup_console
from q_cli.utils.constants import DEFAULT_MODEL, DEFAULT_MAX_TOKENS
from q_cli.utils.helpers import sanitize_context
from q_cli.cli.conversation import run_conversation


def main() -> None:
    """Main entry point for the CLI."""
    parser = setup_argparse()

    # If no args provided (sys.argv has just the script name), print help and exit
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    # Initialize console for output
    console = setup_console()

    # Get API key and config vars from config file
    config_api_key, config_context, config_vars = read_config_file(console)

    # Use API key from args, config file, or environment variable (in that order)
    api_key = args.api_key or config_api_key or os.environ.get("ANTHROPIC_API_KEY")

    # Set model from args, config file, or default
    if not args.model:
        args.model = config_vars.get("MODEL", DEFAULT_MODEL)

    # Set max_tokens from config file or default
    args.max_tokens = int(config_vars.get("MAX_TOKENS", DEFAULT_MAX_TOKENS))

    if not api_key:
        console.print(
            "Error: Anthropic API key not provided. Add to ~/.config/q.conf, set ANTHROPIC_API_KEY environment variable, or use --api-key",
            style="error",
        )
        sys.exit(1)

    # Initialize client
    client = anthropic.Anthropic(api_key=api_key)

    # Set up prompt session for input
    prompt_session = create_prompt_session(console)
    history = prompt_session.history

    # Build and sanitize context from config and files
    context = build_context(args, config_context, console)
    sanitized_context = sanitize_context(context, console)

    # Set up system prompt with context if available
    system_prompt = "You are a helpful AI assistant. Provide accurate, concise answers."

    # Add command execution instructions if not disabled
    if not getattr(args, "no_execute", False):
        system_prompt += """

When appropriate, you can suggest shell commands to help users. Format commands as follows:
```bash
command here
```

For multi-line commands, use backslash at the end of each line for continuation:
```bash
echo "This is a multi-line message" \
  && ls -la \
  && echo "Done"
```

Guidelines for suggesting commands:
1. Only suggest commands when they directly help answer the user's question
2. Explain what each command does before suggesting it
3. Keep commands simple and safe; avoid destructive operations
4. Prefer commands that can be executed locally without special privileges
5. For filesystem operations, prefer relative paths when possible
6. Explain the expected output of commands
"""

    if sanitized_context:
        system_prompt += (
            "\n\nHere is some context that may be helpful:\n" + sanitized_context
        )

    # If confirm-context is specified, show the context and ask for confirmation
    if args.confirm_context and sanitized_context:
        if not confirm_context(prompt_session, system_prompt, console):
            console.print("Context rejected. Exiting.", style="info")
            sys.exit(0)

    # Get initial question from args, file, or prompt
    try:
        question = get_initial_question(args, prompt_session, history)
    except (KeyboardInterrupt, EOFError):
        sys.exit(0)

    # Run the conversation
    run_conversation(client, system_prompt, args, prompt_session, console, question)


if __name__ == "__main__":
    main()
