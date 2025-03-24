"""Conversation handling functionality."""

import os
import sys
from typing import List, Dict, Optional
import anthropic
from prompt_toolkit import PromptSession
from rich.console import Console

from q_cli.utils.constants import SAVE_COMMAND_PREFIX, DEBUG
from q_cli.utils.helpers import handle_api_error
from q_cli.io.input import get_input
from q_cli.io.output import save_response_to_file
from q_cli.utils.helpers import format_markdown
from q_cli.utils.commands import (
    extract_commands_from_response,
    ask_command_confirmation,
    execute_command,
    format_command_output,
    handle_file_creation_command,
    process_file_writes,
    is_file_creation_command,
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
                
                if DEBUG:
                    console.print(f"[yellow]DEBUG: Received model response ({len(response)} chars)[/yellow]")
                    console.print(f"[red]DEBUG RESPONSE: {response}[/red]")

                # Process response, handle URLs, file writes, and update conversation
                processed_response = process_response_with_urls(response, args, console, conversation, client, system_prompt)

                # Check for command suggestions in the response
                # Note: extract_commands_from_response will ignore WRITE_FILE markers
                if not getattr(args, "no_execute", False):
                    # Filter out any file operation result messages from command processing
                    command_response = processed_response
                    
                    # Skip file operation result messages and RUN_SHELL markers
                    file_op_patterns = [
                        "[File written:",
                        "[Failed to write file:",
                        "RUN_SHELL",
                        "```RUN_SHELL"
                    ]
                    
                    # Create a more targeted extract_commands call that ignores file operation messages
                    commands = extract_commands_from_response(command_response)
                    
                    # Additional filtering step for safety
                    filtered_commands = []
                    for cmd in commands:
                        # Skip if it looks like a file operation message
                        if any(pattern in cmd for pattern in file_op_patterns):
                            continue
                        filtered_commands.append(cmd)
                    
                    if filtered_commands:
                        command_results = process_commands(
                            filtered_commands, console, permission_manager
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
                            
                            if DEBUG:
                                console.print(f"[yellow]DEBUG: Received command analysis response ({len(analysis_response)} chars)[/yellow]")
                                console.print(f"[red]DEBUG RESPONSE: {analysis_response}[/red]")

                            # Process analysis response, handle URLs, and update conversation
                            process_response_with_urls(
                                analysis_response, args, console, conversation, client, system_prompt
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
        if os.environ.get("Q_DEBUG") or DEBUG:
            console.print(
                f"[info]History saved to {prompt_session.history.filename}[/info]"
            )
        sys.exit(0)


def process_response_with_urls(
    response: str, args, console: Console, conversation: List[Dict[str, str]], 
    client=None, system_prompt=None
) -> str:
    """
    Process a response from the model, handle any URLs and file writes, and update the conversation.

    Args:
        response: The model's response text
        args: Command line arguments
        console: Console for output
        conversation: Current conversation history
        client: Optional Anthropic client for callbacks
        system_prompt: Optional system prompt for callbacks
        
    Returns:
        The processed response after handling URLs and file writes
    """
    model_url_content = {}
    processed_response = response
    
    # Process any URLs in the response if web fetching is enabled
    if not getattr(args, "no_web", False):
        processed_response, model_url_content = process_urls_in_response(
            processed_response, console
        )
    
    # Clean special markers from response before displaying to user
    from q_cli.utils.commands import remove_special_markers
    display_response = remove_special_markers(processed_response)
    
    # Print formatted response first, before handling file writes
    console.print("")  # Add empty line before response
    
    if not args.no_md:
        console.print(format_markdown(display_response))
    else:
        console.print(display_response)
    console.print("")  # Add empty line after response
    
    # Process any file writing markers in the response if file writing is enabled
    file_results = []
    if not getattr(args, "no_file_write", False):
        # Check if there are any file write markers before showing the processing message
        if WRITE_FILE_MARKER_START in processed_response:
            console.print("[info]Processing file operations...[/info]")
        processed_response, file_results = process_file_writes(processed_response, console)

    # Add the original (unprocessed) response to conversation history
    # This ensures URLs are preserved for context in follow-up questions
    conversation.append({"role": "assistant", "content": response})

    # If we have URL content for the model, create a follow-up message with that content
    if model_url_content and not getattr(args, "no_web", False):
        web_content = "\n\n".join(
            [
                f"Web content fetched from {url}:\n{content}"
                for url, content in model_url_content.items()
            ]
        )

        if web_content:
            web_context_message = (
                "I've fetched additional information from the web "
                "based on your request. Here's what I found:\n\n" + web_content
            )
            conversation.append({"role": "user", "content": web_context_message})
            
            # Make an API call to tell the model about the web content
            if client and system_prompt and not getattr(args, "no_web", False):
                if DEBUG:
                    console.print("[yellow]DEBUG: Sending web fetch results to model...[/yellow]")
                # Use an explicit message to indicate we're processing web content
                console.print("[info]Processing web content...[/info]")
                # Use the status for API call, but with a different message to avoid repetition
                with console.status("[info]Calling API with web content...[/info]"):
                    try:
                        web_result_response = client.messages.create(
                            model=args.model,
                            max_tokens=args.max_tokens,
                            temperature=0,
                            system=system_prompt,
                            messages=conversation,
                        )
                        
                        # Add the model's response to conversation
                        web_ack_response = web_result_response.content[0].text
                        conversation.append({"role": "assistant", "content": web_ack_response})
                        
                        if DEBUG:
                            console.print(f"[green]DEBUG: Received web content response ({len(web_ack_response)} chars)[/green]")
                            console.print(f"[red]DEBUG RESPONSE: {web_ack_response}[/red]")
                            
                        # Update processed_response to include the model's response
                        processed_response = web_ack_response
                        
                        # Display the model's response to the user
                        console.print("")  # Add empty line before response
                        if not args.no_md:
                            console.print(format_markdown(web_ack_response))
                        else:
                            console.print(web_ack_response)
                        console.print("")  # Add empty line after response
                    except Exception as e:
                        error_msg = f"Error sending web results to model: {str(e)}"
                        if DEBUG:
                            console.print(f"[red]DEBUG: {error_msg}[/red]")
                        
                        # Add the error as a message to the conversation so model is aware of the failure
                        error_context_message = f"Error occurred while processing web content: {str(e)}"
                        conversation.append({"role": "user", "content": error_context_message})
                        
                        # Make another API call to get the model's response to the error
                        try:
                            console.print("[info]Getting model's response to error...[/info]")
                            error_response = client.messages.create(
                                model=args.model,
                                max_tokens=args.max_tokens,
                                temperature=0,
                                system=system_prompt,
                                messages=conversation,
                            )
                            
                            # Add the model's response to conversation
                            error_ack_response = error_response.content[0].text
                            conversation.append({"role": "assistant", "content": error_ack_response})
                            
                            if DEBUG:
                                console.print(f"[green]DEBUG: Received error response ({len(error_ack_response)} chars)[/green]")
                                console.print(f"[red]DEBUG RESPONSE: {error_ack_response}[/red]")
                            
                            # Display the model's response to the user
                            console.print("")  # Add empty line before response
                            if not args.no_md:
                                console.print(format_markdown(error_ack_response))
                            else:
                                console.print(error_ack_response)
                            console.print("")  # Add empty line after response
                            
                            # Update processed_response to include the model's response
                            processed_response = error_ack_response
                        except Exception as error_call_exception:
                            if DEBUG:
                                console.print(f"[red]DEBUG: Error getting model response to error: {str(error_call_exception)}[/red]")
    
    # If we have file writing results, create a follow-up message with that information
    if file_results:
        file_messages = []
        for result in file_results:
            if result["success"]:
                file_messages.append(f"Successfully wrote file: {result['file_path']}")
            else:
                file_messages.append(f"Failed to write file {result['file_path']}: {result['stderr']}")
        
        if file_messages:
            file_context_message = (
                "I've processed your file writing requests. Here are the results:\n\n" + 
                "\n".join(file_messages)
            )
            conversation.append({"role": "user", "content": file_context_message})
            
            # Make an API call to tell the model about the file write results
            if client and system_prompt and not getattr(args, "no_file_write", False):
                if DEBUG:
                    console.print("[yellow]DEBUG: Sending file operation results to model...[/yellow]")
                # Use an explicit message to indicate we're processing file results
                console.print("[info]Processing file operation results...[/info]")
                # Use the status for API call, but with a different message to avoid repetition
                with console.status("[info]Calling API with file operation results...[/info]"):
                    try:
                        file_result_response = client.messages.create(
                            model=args.model,
                            max_tokens=args.max_tokens,
                            temperature=0,
                            system=system_prompt,
                            messages=conversation,
                        )
                        
                        # Add the model's acknowledgment to conversation
                        file_ack_response = file_result_response.content[0].text
                        conversation.append({"role": "assistant", "content": file_ack_response})
                        
                        if DEBUG:
                            console.print(f"[green]DEBUG: Received file operations response ({len(file_ack_response)} chars)[/green]")
                            console.print(f"[red]DEBUG RESPONSE: {file_ack_response}[/red]")
                            
                        # Update processed_response to include the model's acknowledgment
                        processed_response = file_ack_response
                        
                        # Display the model's response to the user
                        console.print("")  # Add empty line before response
                        if not args.no_md:
                            console.print(format_markdown(file_ack_response))
                        else:
                            console.print(file_ack_response)
                        console.print("")  # Add empty line after response
                    except Exception as e:
                        error_msg = f"Error sending file results to model: {str(e)}"
                        if DEBUG:
                            console.print(f"[red]DEBUG: {error_msg}[/red]")
                        
                        # Add the error as a message to the conversation so model is aware of the failure
                        error_context_message = f"Error occurred while processing file operations: {str(e)}"
                        conversation.append({"role": "user", "content": error_context_message})
                        
                        # Make another API call to get the model's response to the error
                        try:
                            console.print("[info]Getting model's response to error...[/info]")
                            error_response = client.messages.create(
                                model=args.model,
                                max_tokens=args.max_tokens,
                                temperature=0,
                                system=system_prompt,
                                messages=conversation,
                            )
                            
                            # Add the model's response to conversation
                            error_ack_response = error_response.content[0].text
                            conversation.append({"role": "assistant", "content": error_ack_response})
                            
                            if DEBUG:
                                console.print(f"[green]DEBUG: Received error response ({len(error_ack_response)} chars)[/green]")
                                console.print(f"[red]DEBUG RESPONSE: {error_ack_response}[/red]")
                            
                            # Display the model's response to the user
                            console.print("")  # Add empty line before response
                            if not args.no_md:
                                console.print(format_markdown(error_ack_response))
                            else:
                                console.print(error_ack_response)
                            console.print("")  # Add empty line after response
                            
                            # Update processed_response to include the model's response
                            processed_response = error_ack_response
                        except Exception as error_call_exception:
                            if DEBUG:
                                console.print(f"[red]DEBUG: Error getting model response to error: {str(error_call_exception)}[/red]")

    return processed_response


def handle_file_creation_and_format_result(command: str, console: Console) -> str:
    """
    Handle a file creation command and format the result for display.
    
    Args:
        command: The file creation command
        console: Console for output
        
    Returns:
        Formatted result string
    """
    # Handle the file creation command
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

    return f"Command: cat > {original_cmd}\n{result}"


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

    # Process commands individually
    for command in commands:
        # Skip empty commands or commands with WRITE_FILE markers
        if not command.strip() or WRITE_FILE_MARKER_START in command:
            continue

        # Check if this is a special file creation command (legacy method)
        if command.startswith("__FILE_CREATION__"):
            result = handle_file_creation_and_format_result(command, console)
            results.append(result)
            continue
            
        # Check if this is a file creation command using cat/tee
        file_info = is_file_creation_command(command)
        if file_info["is_file_creation"]:
            console.print(
                f"\n[yellow]File creation via command line is deprecated. Using the WRITE_FILE mechanism is preferred.[/yellow]"
            )
            console.print(
                f"[yellow]To create files, use the <<WRITE_FILE:path/to/file>>content<<WRITE_FILE>> format.[/yellow]"
            )
            # Skip the command to avoid line-by-line file creation
            continue

        # Check if the command is prohibited
        if permission_manager and permission_manager.is_command_prohibited(command):
            error_msg = f"Command '{command}' is prohibited and cannot be executed."
            console.print(f"\n[bold red]{error_msg}[/bold red]")
            # Add this error to the results for the model
            results.append(f"Command: {command}\nError: {error_msg}")
            continue

        # Ask for confirmation if needed
        if permission_manager and permission_manager.needs_permission(command):
            execute, remember = ask_command_confirmation(
                command, console, permission_manager
            )

            if not execute:
                error_msg = "Command execution skipped by user"
                console.print(f"[yellow]{error_msg}[/yellow]")
                # Add this information to the results for the model
                results.append(f"Command: {command}\nStatus: {error_msg}")
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

        # If input is not empty or --no-empty flag is not set, proceed
        if not args.no_empty or question.strip():
            return question
