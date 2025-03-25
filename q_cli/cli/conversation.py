"""Conversation handling functionality."""

import os
import sys
import threading
import time
import signal
from typing import List, Dict, Optional, Callable, Any
import anthropic
from prompt_toolkit import PromptSession
from rich.console import Console

from q_cli.utils.constants import (
    SAVE_COMMAND_PREFIX, DEBUG, HISTORY_PATH,
    ESSENTIAL_PRIORITY, IMPORTANT_PRIORITY, SUPPLEMENTARY_PRIORITY
)
from q_cli.utils.helpers import handle_api_error, format_markdown
from q_cli.utils.context import ContextManager
from q_cli.io.input import get_input
from q_cli.io.output import save_response_to_file
from q_cli.utils.commands import (
    extract_commands_from_response,
    ask_command_confirmation,
    execute_command,
    format_command_output,
    process_file_writes,
    remove_special_markers,
    WRITE_FILE_MARKER_START,
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
    context_manager: Optional[ContextManager] = None,
) -> None:
    """
    Run the continuous conversation loop with Claude.

    Args:
        client: Anthropic client
        system_prompt: System prompt with context
        args: Command line arguments
        prompt_session: PromptSession for input
        console: Console for output
        initial_question: First question to send to Claude
        permission_manager: Optional manager for command permissions
    """
    # Initialize conversation history
    conversation: List[Dict[str, str]] = []
    
    try:
        # Add initial user question to conversation and context manager
        if initial_question.strip():
            conversation.append({"role": "user", "content": initial_question})
            
            # Add to context manager if available
            if context_manager:
                context_manager.add_context(
                    f"User question: {initial_question}",
                    ESSENTIAL_PRIORITY,
                    "Initial question"
                )
            
            # Main conversation loop - continues until explicit exit
            while True:
                try:
                    # If using context manager, update the conversation tokens
                    # and check if we need to optimize
                    current_system_prompt = system_prompt
                    if context_manager and len(conversation) > 3:
                        # For longer conversations, optimize the context
                        if DEBUG:
                            console.print("[info]Optimizing context for long conversation[/info]")
                        context_manager.optimize_context()
                    
                    # Call Claude API with current conversation
                    try:
                        with console.status("[info]Thinking... [Ctrl+C to cancel][/info]"):
                            message = client.messages.create(
                                model=args.model,
                                max_tokens=args.max_tokens,
                                temperature=0,
                                system=current_system_prompt,
                                messages=conversation,  # type: ignore
                            )
                    except KeyboardInterrupt:
                        # Handle Ctrl+C during API call
                        console.print("\n[bold red]Request interrupted by user[/bold red]")
                        # IMPORTANT: We're just dropping the request and continuing back to input
                        # Do NOT add any messages to the conversation
                        # This effectively starts a fresh conversation turn
                        console.print("\n[info]Ask another question, type 'continue' to resume, or type 'exit' to quit[/info]")
                        # Force getting a new user input without sending anything to the model
                        next_question = handle_next_input(args, prompt_session, conversation, console)
                        
                        # Check for exit command
                        if next_question.strip().lower() in ["exit", "quit"]:
                            sys.exit(0)
                        
                        # Add user input to conversation and context manager
                        if next_question.strip():
                            conversation.append({"role": "user", "content": next_question})
                            
                            # Add to context manager if available
                            if context_manager:
                                context_manager.add_context(
                                    f"User question: {next_question}",
                                    ESSENTIAL_PRIORITY,
                                    "User question"
                                )
                        # If empty input and we require non-empty inputs, get a new input
                        elif args.no_empty:
                            continue
                        # Otherwise add the empty input to trigger a Claude response
                        else:
                            conversation.append({"role": "user", "content": next_question})
                        
                        # Important! Start a new iteration of the loop without sending anything
                        continue
                    
                    # Get Claude's response
                    response = message.content[0].text  # type: ignore
                    
                    if DEBUG:
                        console.print(f"[yellow]DEBUG: Received model response ({len(response)} chars)[/yellow]")
                        console.print(f"[red]DEBUG RESPONSE: {response}[/red]")
                    
                    # Add Claude's response to conversation history and context manager
                    conversation.append({"role": "assistant", "content": response})
                    
                    # Add to context manager if available
                    if context_manager:
                        # Add only a summary or first part to save tokens
                        response_summary = response[:500] + "..." if len(response) > 500 else response
                        context_manager.add_context(
                            f"Assistant response: {response_summary}",
                            ESSENTIAL_PRIORITY,
                            "Assistant response"
                        )
                    
                    # Process response for display (handle URL markers, file write markers)
                    display_response = remove_special_markers(response)
                    
                    # Print formatted response
                    console.print("")  # Add empty line before response
                    if not args.no_md:
                        console.print(format_markdown(display_response))
                    else:
                        console.print(display_response)
                    console.print("")  # Add empty line after response
                    
                    # Process operations in the response
                    operation_results = []
                    has_operation_error = False
                    operation_interrupted = False  # Track if an operation was interrupted
                    
                    # If the last message was an interruption, we're already in STOP mode
                    # So we should not process any more operations
                    if len(conversation) > 0 and conversation[-1]["role"] == "user":
                        last_message = conversation[-1]["content"]
                        if "STOP. The operation was cancelled by user" in last_message:
                            operation_interrupted = True
                            console.print("[yellow]Skipping operations due to previous interruption[/yellow]")
                    
                    # 1. Process URLs if web fetching is enabled
                    url_results = None
                    if not getattr(args, "no_web", False) and not operation_interrupted:
                        with console.status("[info]Fetching web content... [Ctrl+C to cancel][/info]"):
                            url_processed_response, url_content, url_has_error = process_urls_in_response(
                                response, console, False
                            )
                        has_operation_error = has_operation_error or url_has_error
                        
                        if url_content:
                            web_content = "\n\n".join(
                                [
                                    f"Web content fetched from {url}:\n{content}"
                                    for url, content in url_content.items()
                                ]
                            )
                            
                            url_results = (
                                "I've fetched additional information from the web "
                                "based on your request. Here's what I found:\n\n" + web_content
                            )
                    
                    # 2. Process file operations if enabled
                    file_results_data = None
                    if not getattr(args, "no_file_write", False) and not operation_interrupted:
                        # Using the status spinner for file operations
                        with console.status("[info]Processing file operations... [Ctrl+C to cancel][/info]") as status:
                            file_processed_response, file_ops_results, file_has_error = process_file_writes(
                                response, console, False
                            )
                        has_operation_error = has_operation_error or file_has_error
                        
                        # Check if any file operations were cancelled by user
                        for result in file_ops_results:
                            if "STOP. The operation was cancelled by user" in result.get("stderr", ""):
                                operation_interrupted = True
                                break
                        
                        if file_ops_results:
                            file_messages = []
                            for result in file_ops_results:
                                if result["success"]:
                                    file_messages.append(f"Successfully wrote file: {result['file_path']}")
                                else:
                                    file_messages.append(f"Failed to write file {result['file_path']}: {result['stderr']}")
                            
                            file_results_data = (
                                "I've processed your file writing requests. Here are the results:\n\n" + 
                                "\n".join(file_messages)
                            )
                    
                    # 3. Process commands if enabled
                    command_results_data = None
                    if not getattr(args, "no_execute", False) and not operation_interrupted:
                        commands = extract_commands_from_response(response)
                        filtered_commands = []
                        
                        # Filter out file operation messages
                        file_op_patterns = [
                            "[File written:",
                            "[Failed to write file:",
                            "RUN_SHELL",
                            "```RUN_SHELL"
                        ]
                        
                        for cmd in commands:
                            if not any(pattern in cmd for pattern in file_op_patterns):
                                filtered_commands.append(cmd)
                        
                        if filtered_commands:
                            with console.status("[info]Processing commands... [Ctrl+C to cancel][/info]"):
                                command_results_str, cmd_has_error = process_commands(
                                    filtered_commands, console, permission_manager, False
                                )
                            has_operation_error = has_operation_error or cmd_has_error
                            
                            # Check if any command was cancelled by the user
                            if command_results_str and "STOP. The operation was cancelled by user" in command_results_str:
                                operation_interrupted = True
                            
                            if command_results_str:
                                command_results_data = get_command_result_prompt(command_results_str)
                    
                    # 4. Display appropriate message for operation status
                    if has_operation_error and not operation_interrupted:
                        # Check if any commands were rejected by user
                        operation_rejected = False
                        if command_results_data and "Command execution skipped by user" in command_results_data:
                            operation_rejected = True
                            console.print("[yellow]Operation rejected[/yellow]")
                        else:
                            console.print("[red]Operation error[/red]")
                    
                    # 5. Combine all operation results
                    if url_results:
                        operation_results.append(url_results)
                    if file_results_data:
                        operation_results.append(file_results_data)
                    if command_results_data:
                        operation_results.append(command_results_data)
                        
                    # If any operation was interrupted, add a clear message to the results
                    if operation_interrupted:
                        stop_message = "STOP. The operation was cancelled by user. Do not proceed with any additional commands or operations. Wait for new instructions from the user."
                        operation_results.append(stop_message)
                    
                    # 6. If we have operation results, add them to conversation as user message
                    if operation_results:
                        combined_results = "\n\n".join(operation_results)
                        conversation.append({"role": "user", "content": combined_results})
                        # Continue loop to let Claude process the results
                        continue
                    
                    # If not in interactive mode and no more operations to process, exit loop
                    if args.no_interactive:
                        break
                    
                    # Get next user input
                    next_question = handle_next_input(args, prompt_session, conversation, console)
                    
                    # Check for exit command
                    if next_question.strip().lower() in ["exit", "quit"]:
                        sys.exit(0)
                    
                    # Add user input to conversation and context manager
                    if next_question.strip():
                        conversation.append({"role": "user", "content": next_question})
                        
                        # Add to context manager if available
                        if context_manager:
                            context_manager.add_context(
                                f"User question: {next_question}",
                                ESSENTIAL_PRIORITY,
                                "User question"
                            )
                    else:
                        # If empty input and we require non-empty inputs, get a new input
                        if args.no_empty:
                            continue
                        # Otherwise add the empty input to trigger a Claude response
                        conversation.append({"role": "user", "content": next_question})
                
                except Exception as e:
                    handle_api_error(e, console)
                    
                    # Add error message to conversation
                    error_message = f"An error occurred: {str(e)}"
                    conversation.append({"role": "user", "content": error_message})
    
    except (KeyboardInterrupt, EOFError):
        # Handle Ctrl+C or Ctrl+D gracefully
        pass
    finally:
        # prompt_toolkit's FileHistory automatically saves history
        if os.environ.get("Q_DEBUG") or DEBUG:
            # Check if history has a filename attribute (FileHistory does)
            history_file = getattr(prompt_session.history, "filename", HISTORY_PATH)
            console.print(
                f"[info]History saved to {history_file}[/info]"
            )
        sys.exit(0)


def process_commands(
    commands: List[str],
    console: Console,
    permission_manager: Optional["CommandPermissionManager"] = None,
    show_errors: bool = True
) -> tuple[Optional[str], bool]:
    """
    Process and execute commands extracted from Claude's response.

    Args:
        commands: List of commands to execute
        console: Console for output
        permission_manager: Optional manager for command permissions
        show_errors: Whether to display error messages to the user

    Returns:
        Tuple containing:
        - Formatted command results, or None if no commands were executed
        - Boolean indicating if any errors occurred
    """
    results = []
    has_error = False

    # Skip if no commands
    if not commands:
        return None, False

    # Process commands individually
    for command in commands:
        # Skip empty commands or commands with WRITE_FILE markers
        if not command.strip() or WRITE_FILE_MARKER_START in command:
            continue

        # Check if the command is prohibited
        if permission_manager and permission_manager.is_command_prohibited(command):
            error_msg = f"Command '{command}' is prohibited and cannot be executed."
            if DEBUG:
                console.print(f"[yellow]DEBUG: {error_msg}[/yellow]")
            # Add this error to the results for the model
            results.append(f"Command: {command}\nError: {error_msg}")
            has_error = True
            continue

        # Ask for confirmation if needed
        if permission_manager and permission_manager.needs_permission(command):
            execute, remember = ask_command_confirmation(
                command, console, permission_manager
            )

            if not execute:
                error_msg = "Command execution skipped by user"
                if DEBUG:
                    console.print(f"[yellow]DEBUG: {error_msg}[/yellow]")
                # Add this information to the results for Claude
                results.append(f"Command: {command}\nStatus: {error_msg}")
                has_error = True
                continue

            # Remember this command type if requested
            if remember and permission_manager:
                permission_manager.approve_command_type(command)
        else:
            # Command is pre-approved
            console.print(f"\n[green]Command '{command}' is pre-approved.[/green]")

        # Execute the command
        console.print(f"[bold green]Executing:[/bold green] {command}")
        return_code, stdout, stderr = execute_command(command, console)
        
        # Check if the command failed
        if return_code != 0:
            has_error = True

        # Format and store the results
        result = format_command_output(return_code, stdout, stderr)
        results.append(f"Command: {command}\n{result}")
        
    # Show a single error message if any command failed and we're set to show errors
    if has_error and show_errors:
        console.print("[red]Operation failed.[/red]")
        
    if results:
        return "\n\n".join(results), has_error
    return None, has_error


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
        question = get_input("Q> ", session=prompt_session)

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

        # Return the question regardless of empty or not
        # The calling function will handle empty inputs based on args.no_empty
        return question