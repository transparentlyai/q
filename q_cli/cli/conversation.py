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
    handle_file_creation_command,
)
from q_cli.utils.permissions import CommandPermissionManager
from q_cli.utils.prompts import get_command_result_prompt
from q_cli.utils.web import process_urls_in_response


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
        console: Console for output
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
                model_url_content = {}
                
                # Process any URLs in the response if web fetching is enabled
                if not getattr(args, "no_web", False):
                    processed_response, model_url_content = process_urls_in_response(response, console)
                else:
                    processed_response = response

                # Print formatted response
                console.print("")  # Add empty line before response
                if not args.no_md:
                    console.print(format_markdown(processed_response))
                else:
                    console.print(processed_response)
                console.print("")  # Add empty line after response

                # Add the original (unprocessed) response to conversation history
                # This ensures URLs are preserved for context in follow-up questions
                conversation.append({"role": "assistant", "content": response})
                
                # If we have URL content for the model, create a follow-up message with that content
                if model_url_content and not getattr(args, "no_web", False):
                    web_content = "\n\n".join([
                        f"Web content fetched from {url}:\n{content}" 
                        for url, content in model_url_content.items()
                    ])
                    
                    if web_content:
                        web_context_message = (
                            "I've fetched additional information from the web "
                            "based on your request. Here's what I found:\n\n" + web_content
                        )
                        conversation.append({"role": "user", "content": web_context_message})

                # Check for command suggestions in the response
                if not getattr(args, "no_execute", False):
                    commands = extract_commands_from_response(response)
                    if commands:
                        command_results = process_commands(
                            commands, console, permission_manager
                        )
                        if command_results:
                            # Add the command results to the conversation
                            follow_up = get_command_result_prompt(command_results)
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

                            # Get Q's analysis
                            analysis_response = analysis.content[0].text
                            
                            # Process any URLs in the analysis response if web fetching is enabled
                            model_url_content = {}
                            if not getattr(args, "no_web", False):
                                processed_analysis, model_url_content = process_urls_in_response(analysis_response, console)
                            else:
                                processed_analysis = analysis_response
                            
                            console.print("")  # Add empty line before response
                            if not args.no_md:
                                console.print(format_markdown(processed_analysis))
                            else:
                                console.print(processed_analysis)
                            console.print("")  # Add empty line after response

                            # Add Q's original analysis to the conversation
                            conversation.append(
                                {"role": "assistant", "content": analysis_response}
                            )
                            
                            # If we have URL content for the model, create a follow-up message with that content
                            if model_url_content and not getattr(args, "no_web", False):
                                web_content = "\n\n".join([
                                    f"Web content fetched from {url}:\n{content}" 
                                    for url, content in model_url_content.items()
                                ])
                                
                                if web_content:
                                    web_context_message = (
                                        "I've fetched additional information from the web "
                                        "based on your request. Here's what I found:\n\n" + web_content
                                    )
                                    conversation.append({"role": "user", "content": web_context_message})

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
    permission_manager: Optional["CommandPermissionManager"] = None,
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
    
    # Skip if no commands
    if not commands:
        return None
        
    # Present the execution plan and ask for confirmation
    from q_cli.utils.commands import ask_execution_plan_confirmation
    
    execute_plan, command_indices = ask_execution_plan_confirmation(
        commands, console, permission_manager
    )
    
    if not execute_plan:
        console.print("[yellow]Command execution plan skipped by user[/yellow]")
        return None
        
    # Determine if we're executing one by one based on previous response
    # 'a' = all at once, 'o' = one by one
    execute_one_by_one = input("\nWould you like to execute all commands at once or one by one? [a/o] ").lower().startswith("o")
    
    # Execute the commands
    for idx in command_indices:
        command = commands[idx]
        
        # Skip empty commands
        if not command.strip():
            continue

        # Check if this is a special file creation command
        if command.startswith("__FILE_CREATION__"):
            # Handle the file creation command specially
            success, stdout, stderr = handle_file_creation_command(command, console)

            # Get the original command for display purposes
            original_cmd = command.split("__")[2]  # Extract file path as the "command"
            if not original_cmd:
                original_cmd = "Create file"

            # Format and store the results
            if success:
                result = f"Exit Code: 0\n\nOutput:\n```\n{stdout}\n```"
            else:
                result = f"Exit Code: 1\n\nErrors:\n```\n{stderr}\n```"

            results.append(f"Command: cat > {original_cmd}\n{result}")
            continue

        # If executing one by one, ask for confirmation for each command
        if execute_one_by_one:
            execute, remember = ask_command_confirmation(
                command, console, permission_manager
            )
            
            if not execute:
                console.print("[yellow]Command execution skipped by user[/yellow]")
                continue
                
            # Remember this command type if requested
            if remember and permission_manager:
                permission_manager.approve_command_type(command)
        else:
            # Check if we need permission for this specific command
            needs_permission = permission_manager and permission_manager.needs_permission(command)
            
            if needs_permission:
                # Still ask for confirmation for commands that need permission
                execute, remember = ask_command_confirmation(
                    command, console, permission_manager
                )
                
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
