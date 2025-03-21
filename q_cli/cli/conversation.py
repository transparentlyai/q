"""Conversation handling functionality."""

import os
import sys
from typing import List, Dict, Optional
import anthropic
from prompt_toolkit import PromptSession
from rich.console import Console

from q_cli.utils.constants import SAVE_COMMAND_PREFIX
from q_cli.utils.helpers import handle_api_error
from q_cli.io.input import get_input, confirm_context
from q_cli.io.output import save_response_to_file
from q_cli.utils.helpers import format_markdown
from q_cli.utils.commands import (
    extract_commands_from_response,
    ask_command_confirmation,
    execute_command,
    format_command_output,
)
from q_cli.utils.permissions import CommandPermissionManager


def run_conversation(
    client: anthropic.Anthropic,
    system_prompt: str,
    args,
    prompt_session: PromptSession,
    console: Console,
    initial_question: str,
    permission_manager: Optional[CommandPermissionManager] = None,
) -> None:
    """
    Run the conversation loop with Q.

    Args:
        client: Anthropic client
        system_prompt: System prompt with context
        args: Command line arguments
        prompt_session: PromptSession for input
        console: Rich console for output
        initial_question: First question to send to Q
    """
    # Initialize conversation history and input history
    conversation = []
    input_history = []
    question = initial_question

    # Process questions (initial and then interactive if enabled)
    try:
        while question:
            # Check for exit command before processing
            if question.strip().lower() in ["exit", "quit"]:
                sys.exit(0)

            # Add user message to conversation and input history
            conversation.append({"role": "user", "content": question})

            # Only add non-empty questions that aren't duplicates of the last entry
            if question.strip() and (
                not input_history or question != input_history[-1]
            ):
                input_history.append(question.strip())

            # Send question to Claude
            try:
                with console.status("[info]Thinking...[/info]"):
                    message = client.messages.create(
                        model=args.model,
                        max_tokens=args.max_tokens,
                        temperature=0,
                        system=system_prompt,
                        messages=conversation,
                    )

                # Get response
                response = message.content[0].text

                # Print formatted response
                console.print("")  # Add empty line before response
                if not args.no_md:
                    console.print(format_markdown(response))
                else:
                    console.print(response)
                console.print("")  # Add empty line after response

                # Add assistant response to conversation history
                conversation.append({"role": "assistant", "content": response})

                # Check for command suggestions in the response
                if not getattr(args, "no_execute", False):
                    commands = extract_commands_from_response(response)
                    if commands:
                        command_results = process_commands(commands, console, permission_manager)
                        if command_results:
                            # Add the command results to the conversation
                            follow_up = f"I ran the command(s) you suggested. Here are the results:\n\n{command_results}"
                            conversation.append({"role": "user", "content": follow_up})

                            # Get Q's analysis of the command results
                            with console.status(
                                "[info]Analyzing command results...[/info]"
                            ):
                                analysis = client.messages.create(
                                    model=args.model,
                                    max_tokens=args.max_tokens,
                                    temperature=0,
                                    system=system_prompt,
                                    messages=conversation,
                                )

                            # Print Q's analysis
                            analysis_response = analysis.content[0].text
                            console.print("")  # Add empty line before response
                            if not args.no_md:
                                console.print(format_markdown(analysis_response))
                            else:
                                console.print(analysis_response)
                            console.print("")  # Add empty line after response

                            # Add Q's analysis to the conversation
                            conversation.append(
                                {"role": "assistant", "content": analysis_response}
                            )

                # If not in interactive mode, exit after first response
                if args.no_interactive:
                    break

                # Get next question and handle empty inputs if --no-empty flag is set
                question = handle_next_input(
                    args, prompt_session, conversation, console
                )

            except Exception as e:
                handle_api_error(e, console)

    except (KeyboardInterrupt, EOFError):
        # Handle Ctrl+C or Ctrl+D gracefully
        pass
    finally:
        # prompt_toolkit's FileHistory automatically saves history
        if os.environ.get("Q_DEBUG"):
            console.print(
                f"[info]History saved to {prompt_session.history.filename}[/info]"
            )
        sys.exit(0)


def process_commands(
    commands: List[str], 
    console: Console,
    permission_manager: Optional['CommandPermissionManager'] = None
) -> Optional[str]:
    """
    Process and execute commands extracted from Q's response.
    
    Args:
        commands: List of commands to execute
        console: Console for output
        permission_manager: Optional manager for command permissions
        
    Returns:
        Formatted command results, or None if no commands were executed
    """
    results = []

    for command in commands:
        # Skip empty commands
        if not command.strip():
            continue

        # Ask for confirmation before executing
        execute, remember = ask_command_confirmation(command, console, permission_manager)
        
        if not execute:
            console.print("[yellow]Command execution skipped by user[/yellow]")
            continue
            
        # Remember this command type if requested
        if remember and permission_manager:
            permission_manager.approve_command_type(command)

        # Execute the command
        console.print(f"[bold green]Executing:[/bold green] {command}")
        return_code, stdout, stderr = execute_command(command, console)

        # Format and store the results
        result = format_command_output(return_code, stdout, stderr)
        results.append(f"Command: {command}\n{result}")

    if results:
        return "\n\n".join(results)
    return None


def handle_next_input(
    args,
    prompt_session: PromptSession,
    conversation: List[Dict[str, str]],
    console: Console,
) -> str:
    """
    Handle the next input from the user, including save commands.

    Args:
        args: Command line arguments
        prompt_session: PromptSession for input
        conversation: Current conversation history
        console: Rich console

    Returns:
        The next question from the user
    """
    while True:
        question = get_input("> ", session=prompt_session)

        # Handle save command
        if question.strip().lower().startswith(SAVE_COMMAND_PREFIX):
            # Extract the file path from the save command
            file_path = question.strip()[len(SAVE_COMMAND_PREFIX) :].strip()

            # Expand the file path (handle ~ and environment variables)
            file_path = os.path.expanduser(file_path)
            file_path = os.path.expandvars(file_path)

            # Get the last response from conversation history
            if len(conversation) >= 2 and conversation[-1]["role"] == "assistant":
                last_response = conversation[-1]["content"]
                if save_response_to_file(last_response, file_path, console):
                    console.print(f"Response saved to {file_path}", style="info")
            else:
                console.print("No response to save", style="warning")

            # Continue to get a new question
            continue

        # If input is not empty or --no-empty flag is not set, proceed
        if not args.no_empty or question.strip():
            return question
