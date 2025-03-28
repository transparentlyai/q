"""Conversation handling functionality."""

import os
import sys
import base64
from typing import List, Dict, Optional, Any
import anthropic
from prompt_toolkit import PromptSession
from rich.console import Console

from q_cli.utils.constants import (
    SAVE_COMMAND_PREFIX,
    DEBUG,
    HISTORY_PATH,
    ESSENTIAL_PRIORITY,
    DEFAULT_MAX_CONTEXT_TOKENS,
)
from q_cli.utils.helpers import handle_api_error, format_markdown
from q_cli.utils.context import ContextManager, num_tokens_from_string
from q_cli.io.input import get_input
from q_cli.io.output import save_response_to_file
from q_cli.utils.commands import (
    extract_commands_from_response,
    ask_command_confirmation,
    execute_command,
    format_command_output,
    process_file_writes,
    process_file_reads,
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
    auto_approve: bool = False,
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
    conversation: List[Dict[str, Any]] = []

    try:
        # Add initial user question to conversation and context manager
        if initial_question.strip():
            conversation.append({"role": "user", "content": initial_question})

            # Add to context manager if available
            if context_manager:
                context_manager.add_context(
                    f"User question: {initial_question}",
                    ESSENTIAL_PRIORITY,
                    "Initial question",
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
                            console.print(
                                "[info]Optimizing context for long conversation[/info]"
                            )
                        context_manager.optimize_context()

                    # Call Claude API with current conversation
                    try:
                        with console.status(
                            "[info]Thinking... [Ctrl+C to cancel][/info]"
                        ):
                            # Call Claude API - the client will automatically handle text vs multimodal
                            message = client.messages.create(
                                model=args.model,
                                max_tokens=args.max_tokens,
                                temperature=0,
                                system=current_system_prompt,
                                messages=conversation,  # type: ignore
                            )
                    except KeyboardInterrupt:
                        # Handle Ctrl+C during API call
                        console.print(
                            "\n[bold red]Request interrupted by user[/bold red]"
                        )
                        # IMPORTANT: We're just dropping the request and continuing back to input
                        # Do NOT add any messages to the conversation
                        # This effectively starts a fresh conversation turn
                        console.print(
                            "\n[info]Ask another question, type 'continue' to resume, or type 'exit' to quit[/info]"
                        )
                        # Force getting a new user input without sending anything to the model
                        next_question = handle_next_input(
                            args, prompt_session, conversation, console
                        )

                        # Check for exit command
                        if next_question.strip().lower() in ["exit", "quit"]:
                            sys.exit(0)

                        # Add user input to conversation and context manager
                        if next_question.strip():
                            conversation.append(
                                {"role": "user", "content": next_question}
                            )

                            # Add to context manager if available
                            if context_manager:
                                context_manager.add_context(
                                    f"User question: {next_question}",
                                    ESSENTIAL_PRIORITY,
                                    "User question",
                                )
                        # If empty input and we require non-empty inputs, get a new input
                        elif args.no_empty:
                            continue
                        # Otherwise add the empty input to trigger a Claude response
                        else:
                            conversation.append(
                                {"role": "user", "content": next_question}
                            )

                        # Important! Start a new iteration of the loop without sending anything
                        continue

                    # Get Claude's response
                    response = message.content[0].text  # type: ignore

                    if DEBUG:
                        console.print(
                            f"[yellow]DEBUG: Received model response ({len(response)} chars)[/yellow]"
                        )
                        console.print(f"[red]DEBUG RESPONSE: {response}[/red]")

                    # Add Claude's response to conversation history and context manager
                    conversation.append({"role": "assistant", "content": response})

                    # Add to context manager if available
                    if context_manager:
                        # Add only a summary or first part to save tokens
                        response_summary = (
                            response[:500] + "..." if len(response) > 500 else response
                        )
                        context_manager.add_context(
                            f"Assistant response: {response_summary}",
                            ESSENTIAL_PRIORITY,
                            "Assistant response",
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
                    operation_results, has_operation_error, multimodal_content = (
                        process_response_operations(
                            response,
                            args,
                            console,
                            conversation,
                            permission_manager,
                            auto_approve,
                        )
                    )

                    # 6. If we have operation results, check size and add them to conversation as user message
                    if operation_results:
                        combined_results = "\n\n".join(operation_results)
                        
                        # Check if results are too large - use a fraction of DEFAULT_MAX_CONTEXT_TOKENS
                        # Calculate approximate token count
                        result_tokens = num_tokens_from_string(combined_results)
                        max_allowed_tokens = int(DEFAULT_MAX_CONTEXT_TOKENS * 0.5)  # Use 50% of max context
                        
                        if result_tokens > max_allowed_tokens:
                            if DEBUG:
                                console.print(f"[yellow]DEBUG: Operation results too large ({result_tokens} tokens), exceeding limit of {max_allowed_tokens} tokens[/yellow]")
                            
                            # Inform Claude about the size issue instead of sending full results
                            size_message = (
                                f"The operation produced a very large result ({result_tokens} tokens) "
                                f"which exceeded the size limit of {max_allowed_tokens} tokens. "
                                "The complete output is available in the terminal, but was too large to send. "
                                "Please work with what's visible in the terminal output above."
                            )
                            
                            # Check if we have multimodal content to include
                            if multimodal_content:
                                content_array = [
                                    {"type": "text", "text": size_message}
                                ]
                                
                                # Add all image/multimodal content
                                for content_item in multimodal_content:
                                    content_array.append(content_item)
                                    
                                # Create the proper message structure for Claude API
                                multimodal_message = {
                                    "role": "user",
                                    "content": content_array
                                }
                                
                                # Add to conversation
                                conversation.append(multimodal_message)
                            else:
                                # Standard text-only message
                                conversation.append(
                                    {"role": "user", "content": size_message}
                                )
                        else:
                            # Results within size limit, process normally
                            # Check if we have multimodal content to include
                            if multimodal_content:
                                # Create a multimodal message with both text and images
                                content_array = [
                                    {"type": "text", "text": combined_results}
                                ]
                                
                                # Add all image/multimodal content
                                for content_item in multimodal_content:
                                    content_array.append(content_item)
                                    
                                # Create the proper message structure for Claude API
                                multimodal_message = {
                                    "role": "user",
                                    "content": content_array
                                }
                                
                                # Add to conversation
                                conversation.append(multimodal_message)
                            else:
                                # Standard text-only message
                                conversation.append(
                                    {"role": "user", "content": combined_results}
                                )
                        # Continue loop to let Claude process the results
                        continue

                    # If not in interactive mode and no more operations to process, exit loop
                    if args.no_interactive:
                        break

                    # Get next user input
                    next_question = handle_next_input(
                        args, prompt_session, conversation, console
                    )

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
                                "User question",
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
            console.print(f"[info]History saved to {history_file}[/info]")
        sys.exit(0)


def process_commands(
    commands: List[str],
    console: Console,
    permission_manager: Optional["CommandPermissionManager"] = None,
    show_errors: bool = True,
    auto_approve: bool = False,
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

        # Check if auto-approve is enabled
        if auto_approve:
            if DEBUG:
                console.print(
                    f"[yellow]DEBUG: Auto-approving command: {command}[/yellow]"
                )
            execute = True
            remember = True
            console.print(f"[bold green]Auto-approved command:[/bold green] {command}")
        # Ask for confirmation if needed and not auto-approving
        elif permission_manager and permission_manager.needs_permission(command):
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


def process_response_operations(
    response: str,
    args,
    console: Console,
    conversation: List[Dict[str, Any]],
    permission_manager: Optional["CommandPermissionManager"] = None,
    auto_approve: bool = False,
) -> tuple[List[str], bool, List[Dict[str, Any]]]:
    """
    Process operations (URL fetching, file operations, commands) in a response.

    Args:
        response: The response from Claude
        args: Command line arguments
        console: Console for output
        conversation: Conversation history
        permission_manager: Permission manager for commands

    Returns:
        Tuple containing:
        - List of operation results
        - Boolean indicating if any errors occurred
        - List of multimodal content items (images, etc.)
    """
    # Initialize variables
    multimodal_content = []
    operation_results = []
    has_operation_error = False
    operation_interrupted = False  # Track if an operation was interrupted

    # If the last message was an interruption, we're already in STOP mode
    # So we should not process any more operations
    if len(conversation) > 0 and conversation[-1]["role"] == "user":
        last_message = conversation[-1]["content"]
        if "STOP. The operation was cancelled by user" in last_message:
            operation_interrupted = True
            console.print(
                "[yellow]Skipping operations due to previous interruption[/yellow]"
            )
    
    # 1. Process URLs if web fetching is enabled
    url_results = None
    if not getattr(args, "no_web", False) and not operation_interrupted:
        with console.status("[info]Fetching web content... [Ctrl+C to cancel][/info]"):
            url_processed_response, url_content, url_has_error, web_multimodal_content = (
                process_urls_in_response(response, console, False)
            )
        has_operation_error = has_operation_error or url_has_error

        # Add any web multimodal content to our main multimodal content list
        if web_multimodal_content:
            multimodal_content.extend(web_multimodal_content)
            
            if DEBUG:
                console.print(f"[yellow]DEBUG: Added {len(web_multimodal_content)} multimodal items from web fetching[/yellow]")

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

    # 2. Process file read operations if enabled
    file_read_results_data = None
    if not getattr(args, "no_file_read", False) and not operation_interrupted:
        # Check for file read operations
        if DEBUG:
            console.print("[yellow]DEBUG: Checking file read operations...[/yellow]")
        file_processed_response, file_read_results, file_read_has_error, multimodal_files = process_file_reads(
            response, console, False
        )
        has_operation_error = has_operation_error or file_read_has_error

        # Handle text file results
        if file_read_results:
            # For text file reads, we want to directly pass the content back to the model
            # so it can work with the file content
            file_read_messages = []
            for result in file_read_results:
                if result["success"]:
                    # Include the full content for successful reads
                    file_read_messages.append(result["stdout"])
                else:
                    file_read_messages.append(
                        f"Failed to read file {result['file_path']}: {result['stderr']}"
                    )

            file_read_results_data = "\n\n".join(file_read_messages)
        
        # Handle multimodal file results (images, binary files)
        if multimodal_files:
            for file_info in multimodal_files:
                if file_info["file_type"] == "image":
                    # For images, we'll create a multimodal message with the image content
                    try:
                        # Get mime type
                        mime_type = file_info["mime_type"] or "image/png"
                        
                        # For Claude API, prepare the image in the right format
                        image_obj = {
                            "type": "image", 
                            "source": {
                                "type": "base64", 
                                "media_type": mime_type,
                                "data": base64.b64encode(file_info["content"]).decode('utf-8')
                            }
                        }
                        
                        # Add to multimodal content list
                        multimodal_content.append(image_obj)
                        
                        if DEBUG:
                            console.print(f"[yellow]DEBUG: Added image {file_info['file_path']} to multimodal content[/yellow]")
                    except Exception as e:
                        if DEBUG:
                            console.print(f"[yellow]DEBUG: Error preparing image: {str(e)}[/yellow]")
                elif file_info["file_type"] == "binary":
                    # For other binary files, we could potentially convert some types later
                    # Currently we'll just skip them for multimodal handling
                    if DEBUG:
                        console.print(f"[yellow]DEBUG: Binary file {file_info['file_path']} not sent as multimodal content[/yellow]")
    
    # 3. Process file write operations if enabled
    file_write_results_data = None
    if not getattr(args, "no_file_write", False) and not operation_interrupted:
        # Check for file write operations - don't use spinner to avoid conflict with approval prompts
        if DEBUG:
            console.print("[yellow]DEBUG: Checking file write operations...[/yellow]")
        file_processed_response, file_write_results, file_write_has_error = process_file_writes(
            response, console, False, auto_approve
        )
        has_operation_error = has_operation_error or file_write_has_error

        # Check if any file operations were cancelled by user
        for result in file_write_results:
            if "STOP. The operation was cancelled by user" in result.get("stderr", ""):
                operation_interrupted = True
                break

        if file_write_results:
            file_write_messages = []
            for result in file_write_results:
                if result["success"]:
                    file_write_messages.append(
                        f"Successfully wrote file: {result['file_path']}"
                    )
                else:
                    file_write_messages.append(
                        f"Failed to write file {result['file_path']}: {result['stderr']}"
                    )

            file_write_results_data = (
                "I've processed your file writing requests. Here are the results:\n\n"
                + "\n".join(file_write_messages)
            )

    # 4. Process commands if enabled
    command_results_data = None
    if not getattr(args, "no_execute", False) and not operation_interrupted:
        commands = extract_commands_from_response(response)
        filtered_commands = []

        # Filter out file operation messages
        file_op_patterns = [
            "[File written:",
            "[Failed to write file:",
            'Q:COMMAND type="shell"',
            "<Q:COMMAND",
        ]

        for cmd in commands:
            if not any(pattern in cmd for pattern in file_op_patterns):
                filtered_commands.append(cmd)

        if filtered_commands:
            # First get user approval for all commands without showing spinner
            # Then process the approved commands with the spinner
            if DEBUG:
                console.print("[yellow]DEBUG: Checking command approvals...[/yellow]")
            command_results_str, cmd_has_error = process_commands(
                filtered_commands, console, permission_manager, False, auto_approve
            )
            has_operation_error = has_operation_error or cmd_has_error

            # Check if any command was cancelled by the user
            if (
                command_results_str
                and "STOP. The operation was cancelled by user" in command_results_str
            ):
                operation_interrupted = True

            if command_results_str:
                command_results_data = get_command_result_prompt(command_results_str)

    # 5. Display appropriate message for operation status
    if has_operation_error and not operation_interrupted:
        # Check if any commands or file operations were rejected by user
        rejection_indicators = [
            "Command execution skipped by user",
            "File writing skipped by user"
        ]
        
        if (command_results_data and any(indicator in command_results_data for indicator in rejection_indicators)) or \
           (file_write_results_data and any(indicator in file_write_results_data for indicator in rejection_indicators)):
            # User deliberately rejected the operation
            console.print("[yellow]Operation skipped[/yellow]")
        else:
            # Actual error occurred
            console.print("[red]Operation error[/red]")

    # 6. Combine all operation results
    if url_results:
        operation_results.append(url_results)
    if file_read_results_data:
        operation_results.append(file_read_results_data)
    if file_write_results_data:
        operation_results.append(file_write_results_data)
    if command_results_data:
        operation_results.append(command_results_data)

    # If any operation was interrupted, add a clear message to the results
    if operation_interrupted:
        stop_message = "STOP. The operation was cancelled by user. Do not proceed with any additional commands or operations. Wait for new instructions from the user."
        operation_results.append(stop_message)

    # Return operation results, error status, and multimodal content
    return operation_results, has_operation_error, multimodal_content


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
