"""Conversation handling functionality."""

import os
import sys
import base64
import time
from typing import List, Dict, Optional, Any
import litellm
from q_cli.utils.client import LLMClient

# All LLM provider interaction is now via LiteLLM
has_anthropic = False
from prompt_toolkit import PromptSession
from rich.console import Console

from q_cli.utils.constants import (
    SAVE_COMMAND_PREFIX,
    RECOVER_COMMAND,
    TRANSPLANT_COMMAND,
    MAX_HISTORY_TURNS,
    get_debug,
    HISTORY_PATH,
    ESSENTIAL_PRIORITY,
    DEFAULT_MAX_CONTEXT_TOKENS,
)

# Global variable to store the system prompt for provider switches
# This ensures the updated prompt is available to new API calls
_GLOBAL_SYSTEM_PROMPT = None

def set_global_system_prompt(prompt: str) -> None:
    """Set the global system prompt for use after provider switches."""
    global _GLOBAL_SYSTEM_PROMPT
    _GLOBAL_SYSTEM_PROMPT = prompt
    
def get_global_system_prompt() -> Optional[str]:
    """Get the global system prompt if set."""
    return _GLOBAL_SYSTEM_PROMPT
from q_cli.utils.helpers import handle_api_error, format_markdown, clean_operation_codeblocks
from q_cli.utils.context import ContextManager, num_tokens_from_string, TokenRateTracker
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
    client: Any,  # Client implementation supporting any LLM provider
    system_prompt: str,
    args,
    prompt_session: PromptSession,
    console: Console,
    initial_question: str,
    permission_manager: Optional[CommandPermissionManager] = None,
    context_manager: Optional[ContextManager] = None,
    auto_approve: bool = False,
    conversation: Optional[List[Dict[str, Any]]] = None,
    session_manager=None,
) -> None:
    """
    Run the continuous conversation loop with the LLM provider.

    Args:
        client: LLM client wrapper
        system_prompt: System prompt with context
        args: Command line arguments
        prompt_session: PromptSession for input
        console: Console for output
        initial_question: First question to send to Claude
        permission_manager: Optional manager for command permissions
        context_manager: Optional context manager
        auto_approve: Whether to auto-approve commands
        conversation: Optional existing conversation to continue
        session_manager: Optional session manager for saving state
    """
    # Initialize conversation history or use provided conversation
    if conversation is None:
        conversation: List[Dict[str, Any]] = []

    # Initialize token rate tracker to monitor rate limits with provider-specific rate limit
    from q_cli.utils.constants import (
        ANTHROPIC_MAX_TOKENS_PER_MIN,
        VERTEXAI_MAX_TOKENS_PER_MIN,
        GROQ_MAX_TOKENS_PER_MIN,
        OPENAI_MAX_TOKENS_PER_MIN,
        DEFAULT_PROVIDER,
    )
    
    # Determine the correct provider based on model name or args
    model = getattr(args, "model", "")
    provider = getattr(args, "provider", DEFAULT_PROVIDER)
    
    # Check if we have a global system prompt from a previous provider switch
    global_system_prompt = get_global_system_prompt()
    
    # Always ensure we have the correct model name, not just the first time
    # Get a clean model name for display (without provider prefix)
    display_model = model
    if '/' in display_model:
        display_model = display_model.split('/', 1)[1]
    
    # Determine whether to use global prompt or fresh prompt
    use_fresh_prompt = False
    
    if global_system_prompt:
        # Use the global system prompt if available, but first verify it has the correct model
        if '{model}' in global_system_prompt:
            # Unsubstituted placeholder - need fresh prompt
            console.print(f"[yellow]Found unsubstituted {model} in global system prompt[/yellow]")
            use_fresh_prompt = True
        elif "my brain is" in global_system_prompt.lower():
            # Check model name with pattern matching
            parts = global_system_prompt.lower().split("my brain is")
            if len(parts) > 1:
                model_in_prompt = parts[1].split(".")[0].strip()
                if get_debug():
                    console.print(f"[dim]Global system prompt references model: {model_in_prompt}[/dim]")
                
                # If there's a mismatch, regenerate the system prompt
                if model_in_prompt != display_model.lower():
                    console.print(f"[bold red]Model mismatch at startup: Prompt says {model_in_prompt} but using {display_model}[/bold red]")
                    use_fresh_prompt = True
                else:
                    # Use the global prompt since it has the correct model
                    system_prompt = global_system_prompt
                    if get_debug():
                        console.print(f"[dim]Using global system prompt with correct model: {model_in_prompt}[/dim]")
            else:
                # Can't determine model in prompt
                console.print("[yellow]Cannot determine model name in global system prompt[/yellow]")
                use_fresh_prompt = True
        else:
            # No recognizable model reference
            console.print("[yellow]Global system prompt doesn't contain expected model reference[/yellow]")
            use_fresh_prompt = True
    else:
        # No global prompt
        use_fresh_prompt = True
        if get_debug():
            console.print("[dim]No global system prompt available, generating fresh prompt[/dim]")
    
    # Generate a fresh prompt if needed
    if use_fresh_prompt:
        # Load the base prompt directly to ensure we're working with the original template
        from q_cli.utils.prompts import get_prompt
        prompt_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts", "base_system_prompt.md")
        system_prompt = get_prompt(prompt_path, model=display_model)
        
        # If we have context, add it back
        if context_manager and context_manager.get_current_context():
            context_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts", "context_prompt.md")
            current_context = context_manager.get_current_context()
            if current_context:
                context_prompt = get_prompt(context_path, context=current_context)
                system_prompt += f"\n\n{context_prompt}"
        
        # Update the context manager
        if context_manager:
            context_manager.set_system_prompt(system_prompt)
            
        if get_debug():
            console.print(f"[dim]Generated fresh system prompt with model: {display_model}[/dim]")
        
        # Also save the new system prompt to session if available
        if session_manager:
            try:
                # Only save context-free version to session for better compatibility
                base_system_prompt = get_prompt(prompt_path, model=display_model)
                session_manager.save_session(
                    conversation=conversation if conversation else [],
                    system_prompt=base_system_prompt,
                    context_manager=None  # Don't save context to session
                )
                if get_debug():
                    console.print("[dim]Updated session with fresh system prompt[/dim]")
            except Exception as e:
                if get_debug():
                    console.print(f"[dim]Failed to save fresh system prompt to session: {str(e)}[/dim]")
    
    # After using the global system prompt, clear it to avoid reuse in future conversations
    set_global_system_prompt(None)
    
    # If model name contains "gemini", it must be VertexAI regardless of args.provider
    if model and "gemini" in model.lower():
        provider = "vertexai"
    
    # Set the appropriate rate limit based on the provider
    if provider == "anthropic" and 'ANTHROPIC_MAX_TOKENS_PER_MIN' in globals():
        max_tokens_per_min = ANTHROPIC_MAX_TOKENS_PER_MIN
    elif provider == "vertexai" and 'VERTEXAI_MAX_TOKENS_PER_MIN' in globals():
        max_tokens_per_min = VERTEXAI_MAX_TOKENS_PER_MIN
    elif provider == "groq" and 'GROQ_MAX_TOKENS_PER_MIN' in globals():
        max_tokens_per_min = GROQ_MAX_TOKENS_PER_MIN
    elif provider == "openai" and 'OPENAI_MAX_TOKENS_PER_MIN' in globals():
        max_tokens_per_min = OPENAI_MAX_TOKENS_PER_MIN
    else:
        # If no rate limit is defined for the provider, disable rate limiting
        max_tokens_per_min = 0
        if get_debug():
            console.print(f"[yellow]No rate limit defined for provider '{provider}'. Rate limiting disabled.[/yellow]")
        
    token_tracker = TokenRateTracker(max_tokens_per_min)
    # Make token_tracker available in globals for access by transplant command
    globals()['token_tracker'] = token_tracker
    
    # Make context_manager available in globals for access by transplant command
    if context_manager:
        globals()['context_manager'] = context_manager

    try:
        # The 'recover' command in interactive mode has been removed.
        # We only process 'recover' as a CLI flag.
        stripped_initial = initial_question.strip().lower()
        if stripped_initial == RECOVER_COMMAND:
            console.print(
                "[yellow]The 'recover' command is no longer available in interactive mode.[/yellow]"
            )
            console.print(
                "[yellow]Please use 'q --recover' from the command line instead.[/yellow]"
            )
            # Get a new initial question
            initial_question = get_input("Q> ", session=prompt_session)
            stripped_initial = initial_question.strip().lower()
        
        # Handle save command as initial input
        if stripped_initial == SAVE_COMMAND_PREFIX.lower() or stripped_initial.startswith(SAVE_COMMAND_PREFIX.lower() + " "):
            console.print("[yellow]There is no previous response to save.[/yellow]")
            initial_question = get_input("Q> ", session=prompt_session)
            stripped_initial = initial_question.strip().lower()

        # Handle transplant command as initial input
        if stripped_initial == TRANSPLANT_COMMAND.lower() or stripped_initial.startswith(TRANSPLANT_COMMAND.lower() + " "):
            # Process the transplant command
            # Debug message to confirm transplant clears conversation history
            console.print("[yellow]Note: Using /transplant will clear all conversation history[/yellow]")
            
            from q_cli.utils.provider_factory import ProviderFactory
            from q_cli.io.config import read_config_file
            from q_cli.utils.constants import SUPPORTED_PROVIDERS
            
            # Get current configuration
            _, _, config_vars = read_config_file(console)
            
            # Check which providers are configured
            configured_providers = []
            for provider in SUPPORTED_PROVIDERS:
                api_key_var = f"{provider.upper()}_API_KEY"
                api_key = config_vars.get(api_key_var) or os.environ.get(api_key_var)
                
                # Special check for VertexAI which needs additional config
                if provider == "vertexai":
                    project_id = config_vars.get("VERTEXAI_PROJECT") or config_vars.get("VERTEX_PROJECT") or os.environ.get("VERTEXAI_PROJECT")
                    location = config_vars.get("VERTEXAI_LOCATION") or config_vars.get("VERTEX_LOCATION") or os.environ.get("VERTEXAI_LOCATION")
                    
                    if api_key and project_id and location:
                        configured_providers.append(provider)
                elif api_key:
                    configured_providers.append(provider)
            
            # Check if any providers are configured
            if not configured_providers:
                console.print("[red]No providers are fully configured. Please add API keys to your config file.[/red]")
                # Get a new initial question
                initial_question = get_input("Q> ", session=prompt_session)
                stripped_initial = initial_question.strip().lower()
            else:
                # Display current provider and model
                from q_cli.utils.constants import DEFAULT_PROVIDER
                
                # First check the model for Gemini pattern
                if args.model and "gemini" in args.model.lower():
                    # If we're using a Gemini model, it HAS to be VertexAI
                    current_provider = "vertexai"
                    current_model = args.model
                elif 'client' in globals() and hasattr(globals()['client'], 'provider'):
                    # Get from client object
                    current_provider = globals()['client'].provider
                else:
                    # Fallback to args
                    current_provider = args.provider or DEFAULT_PROVIDER
                
                # Get model 
                if 'client' in globals() and hasattr(globals()['client'], 'model'):
                    current_model = globals()['client'].model
                else:
                    current_model = args.model
                    
                # Override args for consistency
                args.provider = current_provider
                
                console.print(f"[bold green]Current provider:[/bold green] {current_provider}")
                console.print(f"[bold green]Current model:[/bold green] {current_model}")
                
                # Show available providers
                console.print("\n[bold]Available providers:[/bold]")
                for i, provider in enumerate(configured_providers, 1):
                    console.print(f"{i}. {provider}")
                    
                # Get provider choice
                while True:
                    provider_choice = input(f"Select provider (1-{len(configured_providers)}, or enter to keep current): ").strip()
                    
                    if not provider_choice:
                        # Keep current provider, ask for initial question
                        initial_question = get_input("Q> ", session=prompt_session)
                        stripped_initial = initial_question.strip().lower()
                        break
                        
                    try:
                        provider_idx = int(provider_choice) - 1
                        if 0 <= provider_idx < len(configured_providers):
                            # Valid choice, update provider
                            new_provider = configured_providers[provider_idx]
                            args.provider = new_provider
                            
                            # Get default model for this provider
                            from q_cli.utils.constants import (
                                ANTHROPIC_DEFAULT_MODEL,
                                VERTEXAI_DEFAULT_MODEL,
                                GROQ_DEFAULT_MODEL,
                                OPENAI_DEFAULT_MODEL
                            )
                            
                            if new_provider == "anthropic":
                                default_model = ANTHROPIC_DEFAULT_MODEL
                            elif new_provider == "vertexai":
                                default_model = VERTEXAI_DEFAULT_MODEL
                            elif new_provider == "groq":
                                default_model = GROQ_DEFAULT_MODEL
                            elif new_provider == "openai":
                                default_model = OPENAI_DEFAULT_MODEL
                            else:
                                default_model = ANTHROPIC_DEFAULT_MODEL
                                
                            # Show available models for this provider
                            console.print(f"\n[bold]Default model for {new_provider}:[/bold] {default_model}")
                            console.print("Enter a specific model name or press enter to use the default:")
                            
                            model_choice = input("Model: ").strip()
                            if model_choice:
                                args.model = model_choice
                            else:
                                args.model = default_model
                                
                            # Update max tokens based on provider
                            from q_cli.utils.constants import (
                                ANTHROPIC_MAX_TOKENS,
                                VERTEXAI_MAX_TOKENS,
                                GROQ_MAX_TOKENS,
                                OPENAI_MAX_TOKENS
                            )
                            
                            if new_provider == "anthropic":
                                args.max_tokens = ANTHROPIC_MAX_TOKENS
                            elif new_provider == "vertexai":
                                args.max_tokens = VERTEXAI_MAX_TOKENS
                            elif new_provider == "groq":
                                args.max_tokens = GROQ_MAX_TOKENS
                            elif new_provider == "openai":
                                args.max_tokens = OPENAI_MAX_TOKENS
                                
                            # Initialize new client
                            from q_cli.utils.client import LLMClient
                            
                            # Get API key for the selected provider
                            api_key_var = f"{new_provider.upper()}_API_KEY" 
                            api_key = config_vars.get(api_key_var) or os.environ.get(api_key_var)
                            
                            # Get extra kwargs for VertexAI
                            provider_kwargs = {}
                            if new_provider == "vertexai":
                                project_id = config_vars.get("VERTEXAI_PROJECT") or config_vars.get("VERTEX_PROJECT") or os.environ.get("VERTEXAI_PROJECT")
                                location = config_vars.get("VERTEXAI_LOCATION") or config_vars.get("VERTEX_LOCATION") or os.environ.get("VERTEXAI_LOCATION")
                                provider_kwargs = {
                                    "project_id": project_id,
                                    "location": location
                                }
                                
                            # Create new client
                            try:
                                # Create a new client 
                                new_client = LLMClient(
                                    api_key=api_key,
                                    model=args.model,
                                    provider=new_provider,
                                    **provider_kwargs
                                )
                                # Replace the global client
                                globals()['client'] = new_client
                                
                                # Update all provider-specific configurations
                                from q_cli.utils.constants import (
                                    # Rate limiting constants
                                    ANTHROPIC_MAX_TOKENS_PER_MIN,
                                    VERTEXAI_MAX_TOKENS_PER_MIN,
                                    GROQ_MAX_TOKENS_PER_MIN,
                                    OPENAI_MAX_TOKENS_PER_MIN,
                                    # Context token limits
                                    ANTHROPIC_MAX_CONTEXT_TOKENS,
                                    VERTEXAI_MAX_CONTEXT_TOKENS,
                                    GROQ_MAX_CONTEXT_TOKENS,
                                    OPENAI_MAX_CONTEXT_TOKENS
                                )
                                
                                # Get the token tracker from the parent scope if possible
                                if 'token_tracker' in globals():
                                    # Set the appropriate rate limit based on the new provider
                                    if new_provider == "anthropic" and 'ANTHROPIC_MAX_TOKENS_PER_MIN' in globals():
                                        globals()['token_tracker'].max_tokens_per_min = ANTHROPIC_MAX_TOKENS_PER_MIN
                                    elif new_provider == "vertexai" and 'VERTEXAI_MAX_TOKENS_PER_MIN' in globals():
                                        globals()['token_tracker'].max_tokens_per_min = VERTEXAI_MAX_TOKENS_PER_MIN
                                    elif new_provider == "groq" and 'GROQ_MAX_TOKENS_PER_MIN' in globals():
                                        globals()['token_tracker'].max_tokens_per_min = GROQ_MAX_TOKENS_PER_MIN
                                    elif new_provider == "openai" and 'OPENAI_MAX_TOKENS_PER_MIN' in globals():
                                        globals()['token_tracker'].max_tokens_per_min = OPENAI_MAX_TOKENS_PER_MIN
                                    else:
                                        # If no rate limit is defined for the provider, disable rate limiting
                                        globals()['token_tracker'].max_tokens_per_min = 0
                                        if get_debug():
                                            console.print(f"[yellow]No rate limit defined for provider '{new_provider}'. Rate limiting disabled.[/yellow]")
                                
                                # Update context manager if it exists
                                if 'context_manager' in globals():
                                    # Set the appropriate context token limit based on the new provider
                                    if new_provider == "anthropic":
                                        max_context_tokens = ANTHROPIC_MAX_CONTEXT_TOKENS
                                    elif new_provider == "vertexai":
                                        max_context_tokens = VERTEXAI_MAX_CONTEXT_TOKENS
                                    elif new_provider == "groq":
                                        max_context_tokens = GROQ_MAX_CONTEXT_TOKENS
                                    elif new_provider == "openai":
                                        max_context_tokens = OPENAI_MAX_CONTEXT_TOKENS
                                    else:
                                        max_context_tokens = ANTHROPIC_MAX_CONTEXT_TOKENS
                                        
                                    if hasattr(globals()['context_manager'], 'max_context_tokens') and max_context_tokens is not None:
                                        globals()['context_manager'].max_context_tokens = max_context_tokens
                                        if get_debug():
                                            console.print(f"[dim]Updated context manager max_context_tokens to {max_context_tokens}[/dim]")
                                
                                # Add special message as the first message
                                console.print(f"[bold green]Provider changed to {new_provider} with model {args.model}[/bold green]")
                                
                                # Update the config file with the new provider and model
                                from q_cli.io.config import update_config_provider
                                if update_config_provider(new_provider, console, args.model):
                                    # The update function itself will print a confirmation message
                                    pass
                                else:
                                    console.print(f"[yellow]Note: Could not update config file, changes will only apply to this session[/yellow]")
                                
                                # Ask for the first real question
                                console.print("[bold]Please enter your first question:[/bold]")
                                initial_question = get_input("Q> ", session=prompt_session)
                                stripped_initial = initial_question.strip().lower()
                                break
                                
                            except Exception as e:
                                console.print(f"[red]Error initializing new provider: {str(e)}[/red]")
                                initial_question = get_input("Q> ", session=prompt_session)
                                stripped_initial = initial_question.strip().lower()
                                break
                        else:
                            console.print(f"[red]Invalid choice. Please select 1-{len(configured_providers)}[/red]")
                    except ValueError:
                        console.print("[red]Invalid input. Please enter a number.[/red]")

        # Now process the initial question (either original or new after recovery/transplant)
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
                        if get_debug():
                            console.print(
                                "[info]Optimizing context for long conversation[/info]"
                            )
                        context_manager.optimize_context()

                    # Call Claude API with current conversation
                    try:
                        with console.status(
                            "[info]Thinking... [Ctrl+C to cancel][/info]"
                        ):
                            # Import rate limiting constants
                            from q_cli.utils.constants import RATE_LIMIT_COOLDOWN
                            import time

                            # Retry loop for handling rate limits
                            max_retries = 3
                            retry_count = 0

                            # Calculate approximate token count for this request
                            system_tokens = num_tokens_from_string(
                                current_system_prompt
                            )
                            conversation_tokens = sum(
                                num_tokens_from_string(msg.get("content", ""))
                                for msg in conversation
                            )
                            total_input_tokens = system_tokens + conversation_tokens

                            if get_debug():
                                # Show token usage stats
                                current_usage = token_tracker.get_current_usage()
                                console.print(
                                    f"[dim]Current token usage: {current_usage}/{token_tracker.max_tokens_per_min} tokens in the last minute[/dim]"
                                )
                                console.print(
                                    f"[dim]Request token count estimate: {total_input_tokens} tokens[/dim]"
                                )

                            # Proactively wait if needed to avoid rate limit
                            token_tracker.wait_if_needed(total_input_tokens, console)

                            while retry_count <= max_retries:
                                try:
                                    # CRITICAL FIX: We need to ensure we're using the correct provider
                                    # Use the client's own provider and model rather than args
                                    # because the client has the correct, up-to-date information
                                    client_provider = getattr(client, 'provider', None)
                                    client_model = getattr(client, 'model', None)
                                    
                                    if client_provider and client_model:
                                        # Use the client's own provider/model combination for the call
                                        # Completely override args to ensure consistency
                                        args.provider = client_provider
                                        
                                        # Format model for LiteLLM based on provider - use the centralized helper
                                        from q_cli.config.providers import format_model_for_litellm
                                        
                                        # Get correctly formatted model name for LiteLLM
                                        formatted_model = format_model_for_litellm(client_provider, client_model)
                                        
                                        # Only show reformatting message if there was a change
                                        if formatted_model != client_model:
                                            console.print(f"[yellow]Reformatting model name for LiteLLM: {client_model} → {formatted_model}[/yellow]")
                                        
                                        # Set the model in args
                                        args.model = formatted_model
                                        
                                        if get_debug():
                                            console.print(f"[bold yellow]Using client's provider/model: {client_provider}/{args.model}[/bold yellow]")
                                    
                                    # Make sure we always use the latest client from globals
                                    # This ensures we're always using the most up-to-date client instance
                                    if 'client' in globals():
                                        # Make sure we're getting a valid LLMClient object
                                        global_client = globals()['client']
                                        # Import LLMClient directly for the isinstance check
                                        from q_cli.utils.client import LLMClient as ClientClass
                                        if global_client and isinstance(global_client, ClientClass):
                                            # Update client directly
                                            client = global_client
                                            # Re-fetch provider info
                                            client_provider = getattr(client, 'provider', None)
                                            client_model = getattr(client, 'model', None)
                                            
                                            # Update args to match the client's settings
                                            # This is critical for API calls to work correctly
                                            if client_model:
                                                args.model = client_model
                                            if client_provider:
                                                args.provider = client_provider
                                                
                                            if get_debug():
                                                console.print(f"[dim]Using client from globals: {client_provider}/{client_model}[/dim]")
                                        elif get_debug():
                                            console.print(f"[yellow]Warning: Global client is not a valid LLMClient object[/yellow]")
                                        
                                    # Call LLM API via our client wrapper
                                    if get_debug():
                                        console.print(f"[dim]Calling {client_provider} API with model={args.model}[/dim]")
                                    
                                    # Final check to ensure model prefix matches provider
                                    # This prevents trying to use anthropic/model with vertexai or vice versa
                                    from q_cli.config.providers import format_model_for_litellm
                                    
                                    # Always ensure model format is correct for the current provider
                                    if client_provider:
                                        # Get the correct format for this provider
                                        correctly_formatted_model = format_model_for_litellm(client_provider, args.model)
                                        if correctly_formatted_model != args.model:
                                            args.model = correctly_formatted_model
                                            if get_debug():
                                                console.print(f"[dim]Model format corrected for {client_provider}: {args.model}[/dim]")
                                    
                                    # Prevent "list index out of range" error by ensuring we have at least one message
                                    if not conversation:
                                        conversation.append({"role": "user", "content": "Hello, I'm starting a new conversation."})
                                        console.print("[yellow]Added a default message to empty conversation[/yellow]")
                                        console.print(f"[yellow]Conversation after adding default message: {len(conversation)} messages[/yellow]")
                                        
                                    # Make sure we're using the correct system prompt
                                    system_prompt_to_use = current_system_prompt
                                    
                                    if get_debug():
                                        # Log first 50 chars of system prompt
                                        console.print(f"[dim]Using system prompt: {system_prompt_to_use[:50]}...[/dim]")
                                    
                                    # Get model name for API call
                                    api_model = args.model
                                    if '/' in api_model:
                                        api_model = api_model.split('/', 1)[1]
                                    
                                    # Save prompt to session if session manager is available
                                    if session_manager:
                                        try:
                                            session_manager.save_session(
                                                conversation=conversation,
                                                system_prompt=system_prompt_to_use,
                                                context_manager=context_manager
                                            )
                                            if get_debug():
                                                console.print("[dim]Updated session with system prompt[/dim]")
                                        except Exception as e:
                                            if get_debug():
                                                console.print(f"[dim]Failed to save session: {str(e)}[/dim]")
                                    
                                    # Add option to display the complete system prompt (useful for debugging)
                                    if os.environ.get("Q_DUMP_PROMPT", "0") == "1":
                                        console.print(f"[dim]Complete system prompt available with environment variable Q_DUMP_PROMPT=1[/dim]")
                                    
                                    # Use the best model info for API call first - moved up to avoid scope issues
                                    if hasattr(client, 'model') and client.model:
                                        api_call_model = client.model
                                    else:
                                        api_call_model = args.model
                                    
                                    # Extract clean model name for prompt
                                    clean_model_name = api_call_model
                                    if '/' in clean_model_name:
                                        clean_model_name = clean_model_name.split('/', 1)[1]
                                    
                                    # Start with the global system prompt
                                    system_prompt_to_use = get_global_system_prompt() or ""
                                    
                                    # If no global prompt, load from file
                                    if not system_prompt_to_use:
                                        from q_cli.utils.prompts import get_prompt
                                        prompt_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                                                 "prompts", "base_system_prompt.md")
                                        system_prompt_to_use = get_prompt(prompt_path, model=clean_model_name.lower())
                                    
                                    # Always ensure the model name is correct right before API call
                                    import re
                                    pattern = r'Your are currently using .+ as your primary model'
                                    replacement = f'Your are currently using {clean_model_name.lower()} as your primary model'
                                    system_prompt_to_use = re.sub(pattern, replacement, system_prompt_to_use, flags=re.IGNORECASE)
                                    
                                    # Update global prompt with corrected version for future API calls
                                    set_global_system_prompt(system_prompt_to_use)
                                    
                                    # Use the final modified prompt in the API call
                                    message = client.messages_create(
                                        model=api_call_model,
                                        max_tokens=args.max_tokens,
                                        temperature=0,
                                        system=system_prompt_to_use,
                                        messages=conversation,  # type: ignore
                                    )

                                    # Record token usage with response completion timestamp
                                    response_time = time.time()
                                    if hasattr(message, "usage") and message.usage:
                                        # If the API returns actual usage info, use that
                                        if hasattr(message.usage, "input_tokens"):
                                            token_tracker.add_usage(
                                                message.usage.input_tokens,
                                                response_time,
                                            )
                                        else:
                                            # Otherwise use our estimate
                                            token_tracker.add_usage(
                                                total_input_tokens, response_time
                                            )
                                    else:
                                        # Fall back to our estimate
                                        token_tracker.add_usage(
                                            total_input_tokens, response_time
                                        )

                                    # Success, break out of the retry loop
                                    break

                                except Exception as api_error:
                                    # Handle the error, but don't exit on rate limit
                                    is_rate_limit = handle_api_error(
                                        api_error, console, exit_on_error=False
                                    )

                                    # If it's not a rate limit error or we've used all retries, re-raise
                                    if not is_rate_limit or retry_count >= max_retries:
                                        raise

                                    # It's a rate limit error and we have retries left
                                    retry_count += 1
                                    console.print(
                                        f"[yellow]Retry {retry_count}/{max_retries}: Waiting {RATE_LIMIT_COOLDOWN} seconds before retrying...[/yellow]"
                                    )

                                    # Sleep before retrying
                                    time.sleep(RATE_LIMIT_COOLDOWN)
                                    console.print(
                                        "[yellow]Retrying request...[/yellow]"
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

                    # Get model's response
                    response = message.content[0].text  # type: ignore

                    if get_debug():
                        console.print(
                            f"[dim]Received model response ({len(response)} chars)[/dim]"
                        )

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

                    # Save the session after each assistant response
                    if session_manager:
                        session_manager.save_session(
                            conversation=conversation,
                            system_prompt=system_prompt,
                            context_manager=context_manager,
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
                        # Join the operations (they're already cleaned individually)
                        combined_results = "\n\n".join(operation_results)

                        # Check if results are too large - use a fraction of DEFAULT_MAX_CONTEXT_TOKENS
                        # Calculate approximate token count
                        result_tokens = num_tokens_from_string(combined_results)
                        max_allowed_tokens = int(
                            DEFAULT_MAX_CONTEXT_TOKENS * 0.5
                        )  # Use 50% of max context

                        if result_tokens > max_allowed_tokens:
                            if get_debug():
                                console.print(
                                    f"[yellow]Operation results too large ({result_tokens} tokens), exceeding limit of {max_allowed_tokens} tokens[/yellow]"
                                )

                            # Inform Claude about the size issue instead of sending full results
                            size_message = (
                                f"The operation produced a very large result ({result_tokens} tokens) "
                                f"which exceeded the size limit of {max_allowed_tokens} tokens. "
                                "The complete output is available in the terminal, but was too large to send. "
                                "Please work with what's visible in the terminal output above."
                            )

                            # Check if we have multimodal content to include
                            if multimodal_content:
                                content_array = [{"type": "text", "text": size_message}]

                                # Add all image/multimodal content
                                for content_item in multimodal_content:
                                    content_array.append(content_item)

                                # Create the proper message structure for Claude API
                                multimodal_message = {
                                    "role": "user",
                                    "content": content_array,
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
                                    "content": content_array,
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
                        # When using --recover, we want to force interactive mode
                        if not args.recover:
                            break
                        else:
                            # Debug output
                            if get_debug():
                                console.print(
                                    "[dim]Interactive mode forced for recovery[/dim]"
                                )

                    # Get next user input
                    next_question = handle_next_input(
                        args, prompt_session, conversation, console, session_manager
                    )

                    # Check for exit command
                    if next_question.strip().lower() in ["exit", "quit"]:
                        sys.exit(0)

                    # Check for special internal command marker
                    if next_question.startswith("[INTERNAL_COMMAND_COMPLETED:"):
                        # This is a special message indicating an internal command completed
                        # We should not send this to Claude, just continue to the next user input
                        console.print(
                            "[dim]Session recovery complete. Enter your next message.[/dim]"
                        )
                        continue
                        
                    # Check for special provider change no-notify marker
                    if next_question == "INTERNAL_PROVIDER_CHANGE_NO_NOTIFY":
                        # Skip adding to conversation to avoid notifying the model
                        continue

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

                except litellm.exceptions.APIError as e:
                    # Pass directly to handle_api_error with exit_on_error=True for all API errors
                    # This ensures consistent handling and will exit on non-recoverable errors
                    handle_api_error(e, console)
                # Handle LiteLLM BadRequestError specially
                except litellm.exceptions.BadRequestError as e:
                    console.print(f"[bold red]LiteLLM Error: {str(e)}[/bold red]")
                    if get_debug():
                        console.print(f"[bold red]Error details: {e}[/bold red]")
                    
                    # Special handling for empty message list errors
                    if "list index out of range" in str(e) or "Received Messages=[]" in str(e):
                        console.print("[yellow]This appears to be an error with empty messages. Trying to add a default message.[/yellow]")
                        # Add a default message if the conversation is empty
                        if not conversation:
                            conversation.append({"role": "user", "content": "Hello, I'm starting a new conversation."})
                            console.print("[green]Added a default message. Please try again.[/green]")
                    else:
                        console.print("[yellow]This is likely due to a provider compatibility issue. Please try again with another question.[/yellow]")
                    
                    # Do NOT add the error to the conversation
                # Handle all other exceptions
                except Exception as e:
                    # For non-API errors, handle differently
                    console.print(f"[bold red]Error: {str(e)}[/bold red]")

                    if get_debug():
                        console.print(f"[bold red]Error details: {e}[/bold red]")
                        
                    # Check for common errors which should not be sent to the model
                    # These include provider switching errors and LiteLLM errors
                    provider_switching_errors = [
                        # NoneType errors (common during provider switching)
                        "object of type 'NoneType'",
                        "NoneType has no",
                        "AttributeError: 'NoneType'",
                        
                        # Provider switching
                        "client referenced before assignment",
                        "not initialized",
                        "provider switching",
                        "provider changed",
                        
                        # LiteLLM errors
                        "list index out of range",
                        "BadRequestError",
                        "litellm",
                        "Received Messages=[]",
                        
                        # Provider-specific errors
                        "AnthropicException",
                        "VertexAIException",
                        
                        # Model format errors
                        "anthropic/",
                        "vertex_ai/"
                    ]
                    
                    if any(error_text in str(e) for error_text in provider_switching_errors):
                        console.print(f"[yellow]This is likely due to a provider switching or initialization issue. Please try your question again.[/yellow]")
                        # Do NOT add the error to the conversation - this prevents it from being sent to the model
                        
                        # Clear conversation if it's a provider switching error to reset state
                        if "provider" in str(e).lower() and len(conversation) > 0:
                            console.print("[yellow]Clearing conversation due to provider switching error.[/yellow]")
                            while len(conversation) > 0:
                                conversation.pop()
                    elif "Client not initialized" in str(e) or "NoneType" in str(e):
                        # Special handling for client initialization errors
                        console.print("[yellow]Client initialization error. Attempting to recover...[/yellow]")
                        # Try to recover the client from globals if available
                        if 'client' in globals() and globals()['client'] is not None:
                            global_client = globals()['client']
                            # Import LLMClient directly for the isinstance check
                            from q_cli.utils.client import LLMClient as ClientClass
                            if isinstance(global_client, ClientClass):
                                client = global_client
                                console.print(f"[green]Successfully recovered client: {client.provider}/{client.model}[/green]")
                            else:
                                console.print("[red]Global client is not a valid LLMClient object[/red]")
                        else:
                            console.print("[red]No valid client available in globals[/red]")
                        # Do NOT add this error to the conversation
                    else:
                        # Only add other types of errors to the conversation
                        error_message = f"An error occurred: {str(e)}"
                        conversation.append({"role": "user", "content": error_message})

    except (KeyboardInterrupt, EOFError):
        # Handle Ctrl+C or Ctrl+D gracefully
        pass
    finally:
        # prompt_toolkit's FileHistory automatically saves history
        if get_debug():
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
        auto_approve: Whether to automatically approve all commands (from command line)

    Returns:
        Tuple containing:
        - Formatted command results, or None if no commands were executed
        - Boolean indicating if any errors occurred
    """
    results = []
    has_error = False
    use_auto_approve = auto_approve  # Track local approval state for this batch of commands

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
            if get_debug():
                console.print(f"[yellow]{error_msg}[/yellow]")
            # Add this error to the results for the model
            results.append(f"Command: {command}\nError: {error_msg}")
            has_error = True
            continue

        # Check if auto-approve is enabled (either from command line or previous approve-all selection)
        if use_auto_approve:
            if get_debug():
                console.print(
                    f"[yellow]Auto-approving command: {command}[/yellow]"
                )
            execute = True
            remember = False  # Don't need to remember with auto-approve
            console.print(f"[bold green]Auto-approved command:[/bold green] {command}")
        # Ask for confirmation if needed and not auto-approving
        elif permission_manager and permission_manager.needs_permission(command):
            execute, remember = ask_command_confirmation(
                command, console, permission_manager
            )

            # Special handling for "cancel_all" operation
            if execute == "cancel_all":
                if get_debug():
                    console.print(
                        f"[yellow]User cancelled all operations[/yellow]"
                    )
                # Return empty to avoid sending anything to Claude
                return None, False

            if not execute:
                error_msg = "Command execution skipped by user"
                if get_debug():
                    console.print(f"[yellow]{error_msg}[/yellow]")
                # Add this information to the results for Claude
                results.append(f"Command: {command}\nStatus: {error_msg}")
                has_error = True
                continue

            # Check if the user selected "approve all" option - this uses our time-based system now
            if remember == "approve_all":
                # Enable approve_all mode for future operations in this batch
                use_auto_approve = True
                # Add notification in results to let calling code know approve_all was activated
                results.append("Approve-all mode activated for all operations")
                if get_debug():
                    console.print(
                        f"[yellow]Command approve-all mode activated for this batch[/yellow]"
                    )
            # Remember this command type if requested (the "Y" option) as permanent session approval
            elif remember and permission_manager:
                # For the "Y" option, this adds permanent session approval (not time-based)
                permission_manager.approve_command_type(command)
                if get_debug():
                    console.print(
                        f"[yellow]Command type permanently approved for this session[/yellow]"
                    )
        else:
            # Command is pre-approved
            console.print(f"\n[green]Command '{command}' is pre-approved.[/green]")

        # Execute the command
        console.print(f"[bold green]Executing:[/bold green] {command}")
        # Pass along the permission check result to avoid redundant dangerous command checks
        # when a command is already approved by the permission system
        is_pre_approved = permission_manager and not permission_manager.needs_permission(command)
        return_code, stdout, stderr = execute_command(command, console, skip_dangerous_check=is_pre_approved)

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
        auto_approve: Whether to auto-approve all operations

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
    approve_all = False  # Track if user has chosen to approve all operations

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
            (
                url_processed_response,
                url_content,
                url_has_error,
                web_multimodal_content,
            ) = process_urls_in_response(response, console, False)
        has_operation_error = has_operation_error or url_has_error

        # Add any web multimodal content to our main multimodal content list
        if web_multimodal_content:
            multimodal_content.extend(web_multimodal_content)

            if get_debug():
                console.print(
                    f"[yellow]Added {len(web_multimodal_content)} multimodal items from web fetching[/yellow]"
                )

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
        if get_debug():
            console.print("[yellow]Checking file read operations...[/yellow]")
        (
            file_processed_response,
            file_read_results,
            file_read_has_error,
            multimodal_files,
        ) = process_file_reads(response, console, False)
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
                                "data": base64.b64encode(file_info["content"]).decode(
                                    "utf-8"
                                ),
                            },
                        }

                        # Add to multimodal content list
                        multimodal_content.append(image_obj)

                        if get_debug():
                            console.print(
                                f"[yellow]Added image {file_info['file_path']} to multimodal content[/yellow]"
                            )
                    except Exception as e:
                        if get_debug():
                            console.print(
                                f"[yellow]Error preparing image: {str(e)}[/yellow]"
                            )
                elif file_info["file_type"] == "binary":
                    # For other binary files, we could potentially convert some types later
                    # Currently we'll just skip them for multimodal handling
                    if get_debug():
                        console.print(
                            f"[yellow]Binary file {file_info['file_path']} not sent as multimodal content[/yellow]"
                        )

    # 3. Process file write operations if enabled
    file_write_results_data = None
    if not getattr(args, "no_file_write", False) and not operation_interrupted:
        # Check for file write operations - don't use spinner to avoid conflict with approval prompts
        if get_debug():
            console.print("[yellow]Checking file write operations...[/yellow]")
        file_processed_response, file_write_results, file_write_has_error = (
            process_file_writes(response, console, False, auto_approve, approve_all, permission_manager)
        )
        has_operation_error = has_operation_error or file_write_has_error

        # Check for approve_all flag from file writes
        if file_write_results and len(file_write_results) > 0:
            # Check for approve_all marker in results
            for result in file_write_results:
                if result.get("file_path") == "__approve_all_status__":
                    approve_all = True
                    break

        # Check if any file operations were cancelled by user
        for result in file_write_results:
            # Check for special "cancel_all" marker
            if result.get("success") == "cancel_all":
                if get_debug():
                    console.print(
                        f"[yellow]File operation was cancelled completely by user[/yellow]"
                    )
                # Return empty values to avoid sending anything to Claude
                return [], False, []

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
            if get_debug():
                console.print("[yellow]Checking command approvals...[/yellow]")
            # Use either auto_approve from args or approve_all from file operations
            command_results_str, cmd_has_error = process_commands(
                filtered_commands,
                console,
                permission_manager,
                False,
                auto_approve or approve_all,
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
            "File writing skipped by user",
        ]

        if (
            command_results_data
            and any(
                indicator in command_results_data for indicator in rejection_indicators
            )
        ) or (
            file_write_results_data
            and any(
                indicator in file_write_results_data
                for indicator in rejection_indicators
            )
        ):
            # User deliberately rejected the operation
            console.print("[yellow]Operation skipped[/yellow]")
        else:
            # Actual error occurred
            console.print("[red]Operation error[/red]")

    # 6. Combine all operation results and clean up any markdown code blocks surrounding operations
    if url_results:
        operation_results.append(clean_operation_codeblocks(url_results))
    if file_read_results_data:
        operation_results.append(clean_operation_codeblocks(file_read_results_data))
    if file_write_results_data:
        operation_results.append(clean_operation_codeblocks(file_write_results_data))
    if command_results_data:
        operation_results.append(clean_operation_codeblocks(command_results_data))

    # If any operation was interrupted, add a clear message to the results
    if operation_interrupted:
        stop_message = "STOP. The operation was cancelled by user. Do not proceed with any additional commands or operations. Wait for new instructions from the user."
        operation_results.append(stop_message)

    # Return operation results, error status, and multimodal content
    return operation_results, has_operation_error, multimodal_content


def handle_next_input(
    args,
    prompt_session: PromptSession,
    conversation: List[Dict[str, Any]],
    console: Console,
    session_manager=None,
) -> str:
    """
    Handle the next input from the user, including save commands.

    Args:
        args: Command line arguments
        prompt_session: PromptSession for input
        conversation: Current conversation history
        console: Rich console
        session_manager: Optional session manager for special commands

    Returns:
        The next question from the user
    """
    while True:
        question = get_input("Q> ", session=prompt_session)

        # The 'recover' command in interactive mode has been removed

        # Handle save command
        stripped_question = question.strip().lower()
        if stripped_question == SAVE_COMMAND_PREFIX.lower() or stripped_question.startswith(SAVE_COMMAND_PREFIX.lower() + " "):
            # Extract the file path from the save command
            file_path = question.strip()[len(SAVE_COMMAND_PREFIX):].strip()

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
            
        # Handle transplant command to change provider/model
        if stripped_question == TRANSPLANT_COMMAND.lower() or stripped_question.startswith(TRANSPLANT_COMMAND.lower() + " "):
            # Debug message to confirm transplant clears conversation history
            console.print("[yellow]Note: Using /transplant will clear all conversation history[/yellow]")
            
            from q_cli.utils.provider_factory import ProviderFactory
            from q_cli.io.config import read_config_file
            from q_cli.utils.constants import SUPPORTED_PROVIDERS
            
            # Get current configuration
            _, _, config_vars = read_config_file(console)
            
            # Check which providers are configured
            configured_providers = []
            for provider in SUPPORTED_PROVIDERS:
                api_key_var = f"{provider.upper()}_API_KEY"
                api_key = config_vars.get(api_key_var) or os.environ.get(api_key_var)
                
                # Special check for VertexAI which needs additional config
                if provider == "vertexai":
                    project_id = config_vars.get("VERTEXAI_PROJECT") or config_vars.get("VERTEX_PROJECT") or os.environ.get("VERTEXAI_PROJECT")
                    location = config_vars.get("VERTEXAI_LOCATION") or config_vars.get("VERTEX_LOCATION") or os.environ.get("VERTEXAI_LOCATION")
                    
                    if api_key and project_id and location:
                        configured_providers.append(provider)
                elif api_key:
                    configured_providers.append(provider)
            
            # Check if any providers are configured
            if not configured_providers:
                console.print("[red]No providers are fully configured. Please add API keys to your config file.[/red]")
                continue
                
            # Display current provider and model 
            from q_cli.utils.constants import DEFAULT_PROVIDER
            
            # First check the model for Gemini pattern
            if args.model and "gemini" in args.model.lower():
                # If we're using a Gemini model, it HAS to be VertexAI
                current_provider = "vertexai"
                current_model = args.model
            elif 'client' in globals() and globals()['client'] is not None:
                client_obj = globals()['client']
                # Check provider attribute
                if hasattr(client_obj, 'provider') and client_obj.provider is not None:
                    current_provider = client_obj.provider
                else:
                    # If client exists but has no provider attribute
                    current_provider = args.provider or DEFAULT_PROVIDER
                
                # Check model attribute  
                if hasattr(client_obj, 'model') and client_obj.model is not None:
                    current_model = client_obj.model
                else:
                    current_model = args.model
            else:
                # No client found, use args
                current_provider = args.provider or DEFAULT_PROVIDER
                current_model = args.model
            
            # Make sure args is updated to match what we detected
            args.provider = current_provider
            
            console.print(f"[bold green]Current provider:[/bold green] {current_provider}")
            console.print(f"[bold green]Current model:[/bold green] {current_model}")
            
            # Show available providers
            console.print("\n[bold]Available providers:[/bold]")
            for i, provider in enumerate(configured_providers, 1):
                console.print(f"{i}. {provider}")
                
            # Get provider choice
            while True:
                provider_choice = input(f"Select provider (1-{len(configured_providers)}, or enter to keep current): ").strip()
                
                if not provider_choice:
                    # Keep current provider
                    break
                    
                try:
                    provider_idx = int(provider_choice) - 1
                    if 0 <= provider_idx < len(configured_providers):
                        # Valid choice, update provider
                        new_provider = configured_providers[provider_idx]
                        args.provider = new_provider
                        
                        # Get default model for this provider
                        from q_cli.utils.constants import (
                            ANTHROPIC_DEFAULT_MODEL,
                            VERTEXAI_DEFAULT_MODEL,
                            GROQ_DEFAULT_MODEL,
                            OPENAI_DEFAULT_MODEL
                        )
                        
                        if new_provider == "anthropic":
                            default_model = ANTHROPIC_DEFAULT_MODEL
                        elif new_provider == "vertexai":
                            default_model = VERTEXAI_DEFAULT_MODEL
                        elif new_provider == "groq":
                            default_model = GROQ_DEFAULT_MODEL
                        elif new_provider == "openai":
                            default_model = OPENAI_DEFAULT_MODEL
                        else:
                            default_model = ANTHROPIC_DEFAULT_MODEL
                            
                        # Show available models for this provider
                        console.print(f"\n[bold]Default model for {new_provider}:[/bold] {default_model}")
                        console.print("Enter a specific model name or press enter to use the default:")
                        
                        model_choice = input("Model: ").strip()
                        if model_choice:
                            args.model = model_choice
                        else:
                            args.model = default_model
                            
                        # Update max tokens based on provider
                        from q_cli.utils.constants import (
                            ANTHROPIC_MAX_TOKENS,
                            VERTEXAI_MAX_TOKENS,
                            GROQ_MAX_TOKENS,
                            OPENAI_MAX_TOKENS
                        )
                        
                        if new_provider == "anthropic":
                            args.max_tokens = ANTHROPIC_MAX_TOKENS
                        elif new_provider == "vertexai":
                            args.max_tokens = VERTEXAI_MAX_TOKENS
                        elif new_provider == "groq":
                            args.max_tokens = GROQ_MAX_TOKENS
                        elif new_provider == "openai":
                            args.max_tokens = OPENAI_MAX_TOKENS
                            
                        # Initialize new client
                        from q_cli.utils.client import LLMClient
                        
                        # Get API key for the selected provider
                        api_key_var = f"{new_provider.upper()}_API_KEY" 
                        api_key = config_vars.get(api_key_var) or os.environ.get(api_key_var)
                        
                        # Get extra kwargs for VertexAI
                        provider_kwargs = {}
                        if new_provider == "vertexai":
                            project_id = config_vars.get("VERTEXAI_PROJECT") or config_vars.get("VERTEX_PROJECT") or os.environ.get("VERTEXAI_PROJECT")
                            location = config_vars.get("VERTEXAI_LOCATION") or config_vars.get("VERTEX_LOCATION") or os.environ.get("VERTEXAI_LOCATION")
                            provider_kwargs = {
                                "project_id": project_id,
                                "location": location
                            }
                            
                        # Create new client
                        try:
                            # Format the model name for LiteLLM compatibility
                            from q_cli.config.providers import format_model_for_litellm
                            
                            # First format the model name for the provider
                            formatted_model = format_model_for_litellm(new_provider, args.model)
                            
                            # Only show formatting message if it changed
                            if formatted_model != args.model:
                                console.print(f"[yellow]Reformatting model name for LiteLLM: {args.model} → {formatted_model}[/yellow]")
                                args.model = formatted_model
                                
                            # CRITICAL: Before initializing client, immediately reload the system prompt
                            # with the correct model to avoid timing issues
                            from q_cli.utils.prompts import get_prompt
                            prompt_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                                      "prompts", "base_system_prompt.md")
                            
                            # Get clean model name for prompt
                            clean_model = args.model
                            if '/' in clean_model:
                                clean_model = clean_model.split('/', 1)[1]
                                
                            console.print(f"[bold green]Preemptively reloading system prompt with model {clean_model}[/bold green]")
                            
                            # Get fresh prompt and update all references
                            fresh_system_prompt = get_prompt(prompt_path, model=clean_model.lower())
                            current_system_prompt = fresh_system_prompt
                            set_global_system_prompt(fresh_system_prompt)
                            
                            
                            # Initialize the client after updating the prompt
                            client = LLMClient(
                                api_key=api_key,
                                model=args.model,
                                provider=new_provider,
                                **provider_kwargs
                            )
                            
                            # Replace the client reference in globals so LLM calls use the new provider/model
                            console.print("[bold]Upgrading client to use new provider...[/bold]")
                            # Store the old client reference to avoid garbage collection issues
                            old_client = globals().get('client')
                            
                            # Set the client in the global namespace, ensuring it completely replaces the previous client
                            globals()['client'] = client
                            
                            # CRITICAL: Also update this module's client reference
                            # This is crucial for future API calls in this conversation session
                            # No need for nonlocal since client is a parameter
                            client = globals()['client']
                            
                            # Verify client has the correct settings
                            console.print(f"[bold green]Client successfully initialized:[/bold green]")
                            console.print(f"  Provider: {client.provider}")
                            console.print(f"  Model: {client.model}")
                            console.print(f"  Max tokens: {args.max_tokens}")
                            
                            # Force consistency by updating args to match client settings
                            args.provider = client.provider
                            args.model = client.model
                            
                            # Update all provider-specific configurations
                            from q_cli.utils.constants import (
                                # Rate limiting constants
                                ANTHROPIC_MAX_TOKENS_PER_MIN,
                                VERTEXAI_MAX_TOKENS_PER_MIN,
                                GROQ_MAX_TOKENS_PER_MIN,
                                OPENAI_MAX_TOKENS_PER_MIN,
                                # Context token limits
                                ANTHROPIC_MAX_CONTEXT_TOKENS,
                                VERTEXAI_MAX_CONTEXT_TOKENS,
                                GROQ_MAX_CONTEXT_TOKENS,
                                OPENAI_MAX_CONTEXT_TOKENS
                            )
                            
                            # Get the token tracker from the parent scope if possible
                            if 'token_tracker' in globals():
                                # Set the appropriate rate limit based on the new provider
                                if new_provider == "anthropic" and 'ANTHROPIC_MAX_TOKENS_PER_MIN' in globals():
                                    globals()['token_tracker'].max_tokens_per_min = ANTHROPIC_MAX_TOKENS_PER_MIN
                                elif new_provider == "vertexai" and 'VERTEXAI_MAX_TOKENS_PER_MIN' in globals():
                                    globals()['token_tracker'].max_tokens_per_min = VERTEXAI_MAX_TOKENS_PER_MIN
                                elif new_provider == "groq" and 'GROQ_MAX_TOKENS_PER_MIN' in globals():
                                    globals()['token_tracker'].max_tokens_per_min = GROQ_MAX_TOKENS_PER_MIN
                                elif new_provider == "openai" and 'OPENAI_MAX_TOKENS_PER_MIN' in globals():
                                    globals()['token_tracker'].max_tokens_per_min = OPENAI_MAX_TOKENS_PER_MIN
                                else:
                                    # If no rate limit is defined for the provider, disable rate limiting
                                    globals()['token_tracker'].max_tokens_per_min = 0
                                    if get_debug():
                                        console.print(f"[yellow]No rate limit defined for provider '{new_provider}'. Rate limiting disabled.[/yellow]")
                            
                            # Update context manager if it exists
                            if 'context_manager' in globals():
                                # Set the appropriate context token limit based on the new provider
                                if new_provider == "anthropic":
                                    max_context_tokens = ANTHROPIC_MAX_CONTEXT_TOKENS
                                elif new_provider == "vertexai":
                                    max_context_tokens = VERTEXAI_MAX_CONTEXT_TOKENS
                                elif new_provider == "groq":
                                    max_context_tokens = GROQ_MAX_CONTEXT_TOKENS
                                elif new_provider == "openai":
                                    max_context_tokens = OPENAI_MAX_CONTEXT_TOKENS
                                else:
                                    max_context_tokens = ANTHROPIC_MAX_CONTEXT_TOKENS
                                    
                                if hasattr(globals()['context_manager'], 'max_context_tokens') and max_context_tokens is not None:
                                    globals()['context_manager'].max_context_tokens = max_context_tokens
                                    if get_debug():
                                        console.print(f"[dim]Updated context manager max_context_tokens to {max_context_tokens}[/dim]")
                            
                            # Add special message for the model indicating the change
                            console.print(f"[bold green]Provider changed to {new_provider} with model {args.model}[/bold green]")
                            
                            # Update the config file with the new provider and model
                            from q_cli.io.config import update_config_provider
                            if update_config_provider(new_provider, console, args.model):
                                # The update function itself will print a confirmation message
                                pass
                            else:
                                console.print(f"[yellow]Note: Could not update config file, changes will only apply to this session[/yellow]")
                            
                            # CRITICAL: Update parent function's client reference for subsequent API calls
                            # This ensures the parent scope uses our new client instance
                            # No need for nonlocal since client is a parameter
                            client = globals()['client']
                            
                            # We've already loaded the system prompt earlier with the correct model
                            # The current_system_prompt should already be set correctly from the earlier load
                            
                            # Get clean model name (without provider prefix) for verification
                            clean_current_model = args.model
                            if '/' in clean_current_model:
                                clean_current_model = clean_current_model.split('/', 1)[1]
                            
                            # Just to be extra safe, log what's currently in the prompt
                            if "currently using" in current_system_prompt:
                                model_line = [line for line in current_system_prompt.split("\n") if "currently using" in line.lower()]
                                if model_line:
                                    console.print(f"[bold yellow]Model in system prompt: {model_line[0]}[/bold yellow]")
                                    
                                    # Verify we have the correct model in the prompt
                                    if clean_current_model.lower() not in model_line[0].lower():
                                        console.print(f"[bold red]Model mismatch in system prompt, forcing update to {clean_current_model.lower()}[/bold red]")
                                        
                                        # Force direct replacement
                                        import re
                                        pattern = r'Your are currently using .+ as your primary model'
                                        replacement = f'Your are currently using {clean_current_model.lower()} as your primary model'
                                        current_system_prompt = re.sub(pattern, replacement, current_system_prompt, flags=re.IGNORECASE)
                                        
                                        # Double check
                                        model_line = [line for line in current_system_prompt.split("\n") if "currently using" in line.lower()]
                                        if model_line:
                                            console.print(f"[bold green]Updated model in system prompt: {model_line[0]}[/bold green]")
                            
                            # The current_system_prompt is already properly set by get_prompt above
                            
                            # IMPORTANT: COMPLETELY reset the entire context and system prompt
                            # We want to start fresh with NO remnants of the old provider
                            
                            # 1. Clear ALL context items
                            if context_manager:
                                # Completely reset ALL context items to remove any old model references
                                from q_cli.utils.constants import (
                                    ESSENTIAL_PRIORITY, 
                                    IMPORTANT_PRIORITY, 
                                    SUPPLEMENTARY_PRIORITY
                                )
                                # Reset all context items and any history/tracking they might contain
                                context_manager.context_items = {
                                    ESSENTIAL_PRIORITY: [],
                                    IMPORTANT_PRIORITY: [],
                                    SUPPLEMENTARY_PRIORITY: []
                                }
                                
                                # 2. Set a completely fresh system prompt with NO context
                                context_manager.set_system_prompt(current_system_prompt)
                                console.print("[yellow]Reset context manager to use new provider[/yellow]")
                            
                            # 3. The current_system_prompt is already set correctly from above
                                
                            # Set global system prompt for future API calls
                            set_global_system_prompt(current_system_prompt)
                                
                            # Force a complete restart of the conversation loop with the new client
                            console.print("[yellow]Provider changed successfully. Starting new conversation with the new provider...[/yellow]")
                            
                            # Update context manager's system prompt with the already reloaded system prompt
                            if context_manager:
                                context_manager.set_system_prompt(current_system_prompt)
                                console.print("[yellow]Updated context manager with fresh system prompt[/yellow]")
                            
                            # CRITICAL: Completely reset ALL conversation history to start fresh
                            # Empty the conversation list in-place to maintain the reference
                            console.print(f"[yellow]Conversation history before clearing: {len(conversation)} messages[/yellow]")
                            conversation.clear()
                            console.print("[bold red]Conversation history cleared after transplant to new provider[/bold red]")
                            console.print(f"[yellow]Conversation history after clearing: {len(conversation)} messages[/yellow]")
                            
                            # Also reset any session state that might be storing old conversation data
                            if session_manager:
                                try:
                                    session_manager.clear_session()
                                    console.print("[yellow]Session history cleared[/yellow]")
                                    
                                    # Force save an empty session with the new system prompt to ensure
                                    # persistence of the correct prompt even after provider switch
                                    session_manager.save_session(
                                        conversation=[],
                                        system_prompt=current_system_prompt,
                                        context_manager=None
                                    )
                                    console.print("[bold green]New empty session saved with updated system prompt[/bold green]")
                                except Exception as e:
                                    if get_debug():
                                        console.print(f"[dim]Failed to clear/save session: {str(e)}[/dim]")
                            
                            # Add a log message about the conversation reset
                            console.print("[bold green]Conversation history completely reset for new provider[/bold green]")
                            return "INTERNAL_PROVIDER_CHANGE_NO_NOTIFY"
                            
                        except Exception as e:
                            console.print(f"[red]Error initializing new provider: {str(e)}[/red]")
                            break
                    else:
                        console.print(f"[red]Invalid choice. Please select 1-{len(configured_providers)}[/red]")
                except ValueError:
                    console.print("[red]Invalid input. Please enter a number.[/red]")
            
            # Special case - use a marker to avoid sending anything to the model
            continue

        # Return the question regardless of empty or not
        # The calling function will handle empty inputs based on args.no_empty
        return question
