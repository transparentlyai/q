"""Configuration manager for q_cli.

This module provides a unified interface for loading, validating, and accessing
configuration from multiple sources (config files, environment variables, etc.).
"""

import os
import re
import json
from typing import Dict, Any, Tuple, Optional, List, Set
from rich.console import Console

from q_cli.config.providers import (
    DEFAULT_PROVIDER,
    SUPPORTED_PROVIDERS,
    get_provider_env_vars,
    get_default_model,
    get_max_tokens
)
from q_cli.config.commands import (
    parse_command_list
)
from q_cli.utils.constants import CONFIG_PATH


class ConfigManager:
    """Configuration manager for q_cli.
    
    Handles loading and accessing configuration from multiple sources:
    1. Command line arguments
    2. Config file
    3. Environment variables
    4. Default values
    """
    
    def __init__(self, console: Optional[Console] = None):
        """Initialize the configuration manager.
        
        Args:
            console: Rich console for output
        """
        self.console = console or Console()
        self.config_vars: Dict[str, Any] = {}
        self.api_key: Optional[str] = None
        self.context: Optional[str] = None
        
    def load_config(self) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
        """Load configuration from file.
        
        Returns:
            Tuple containing:
            - API key
            - Context
            - Dictionary of configuration variables
        """
        return self._read_config_file()
        
    def _read_config_file(self) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
        """Read configuration from file.
        
        Returns:
            Tuple containing:
            - API key (may be None)
            - Context (may be None)
            - Dictionary of configuration variables
        """
        api_key = None
        context = None
        config_vars: Dict[str, Any] = {}
        
        try:
            # Check if config file exists
            if not os.path.exists(CONFIG_PATH):
                if os.path.exists(os.path.dirname(CONFIG_PATH)):
                    # Directory exists but file doesn't, create empty file
                    with open(CONFIG_PATH, "w") as f:
                        f.write("# Q CLI Configuration\n")
                    self.console.print(f"Created empty config file at {CONFIG_PATH}")
                else:
                    # Directory doesn't exist, create it
                    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
                    # Create empty file
                    with open(CONFIG_PATH, "w") as f:
                        f.write("# Q CLI Configuration\n")
                    self.console.print(f"Created empty config file at {CONFIG_PATH}")
                
                # Return empty config
                return None, None, {}
            
            # Read config file
            with open(CONFIG_PATH, "r") as f:
                lines = f.readlines()
                
            # Process each line
            for line in lines:
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue
                
                # Check for API_KEY or context lines
                if line.startswith("API_KEY="):
                    api_key = line[8:].strip()
                elif line.startswith("CONTEXT="):
                    context = line[8:].strip()
                elif "=" in line:
                    # Process other config variables
                    key, value = line.split("=", 1)
                    config_vars[key.strip()] = value.strip()
            
            # Store the configuration
            self.api_key = api_key
            self.context = context
            self.config_vars = config_vars
            
            return api_key, context, config_vars
            
        except Exception as e:
            self.console.print(f"[yellow]Error reading config file: {str(e)}[/yellow]")
            # Return empty config on error
            return None, None, {}
            
    def validate_config(self) -> bool:
        """Validate configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        # Check for required provider-specific configuration
        provider = self.config_vars.get("PROVIDER", DEFAULT_PROVIDER)
        
        if provider.lower() not in map(str.lower, SUPPORTED_PROVIDERS):
            self.console.print(f"[bold red]Error: Provider '{provider}' is not supported.[/bold red]")
            self.console.print(f"[bold red]Supported providers: {', '.join(SUPPORTED_PROVIDERS)}[/bold red]")
            return False
            
        # Validate provider-specific configuration
        if provider.lower() == "vertexai":
            # VertexAI requires project_id and location
            project_id = (
                self.config_vars.get("VERTEXAI_PROJECT")
                or self.config_vars.get("VERTEX_PROJECT")
                or os.environ.get("VERTEXAI_PROJECT")
                or os.environ.get("VERTEX_PROJECT")
            )
            location = (
                self.config_vars.get("VERTEXAI_LOCATION")
                or self.config_vars.get("VERTEX_LOCATION")
                or os.environ.get("VERTEXAI_LOCATION")
                or os.environ.get("VERTEX_LOCATION")
            )
            
            if not project_id:
                self.console.print("[bold red]Error: VertexAI provider requires a project_id.[/bold red]")
                self.console.print("[bold red]Add VERTEXAI_PROJECT to config or set VERTEXAI_PROJECT environment variable.[/bold red]")
                return False
                
            if not location:
                self.console.print("[bold red]Error: VertexAI provider requires a location.[/bold red]")
                self.console.print("[bold red]Add VERTEXAI_LOCATION to config or set VERTEXAI_LOCATION environment variable.[/bold red]")
                return False
        
        return True
        
    def get_provider_settings(self, args: Any) -> Tuple[str, Optional[str], Dict[str, Any]]:
        """Get provider-specific settings from configuration.
        
        Args:
            args: Command line arguments
            
        Returns:
            Tuple containing:
            - Provider name
            - API key (may be None)
            - Dictionary of provider-specific kwargs
        """
        # Get provider from args, config file, or default
        provider = args.provider or self.config_vars.get("PROVIDER", DEFAULT_PROVIDER)
        
        # Initialize provider_kwargs for any provider-specific settings
        provider_kwargs = {}
        
        # Get API key based on provider
        if args.api_key:
            # Use API key from args
            api_key = args.api_key
        elif provider.lower() == "anthropic":
            api_key = self.config_vars.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        elif provider.lower() == "vertexai":
            api_key = self.config_vars.get("VERTEXAI_API_KEY") or os.environ.get("VERTEXAI_API_KEY")
            
            # Handle VertexAI project ID from config or environment
            project_id = (
                self.config_vars.get("VERTEXAI_PROJECT")
                or self.config_vars.get("VERTEX_PROJECT")
                or os.environ.get("VERTEXAI_PROJECT")
                or os.environ.get("VERTEX_PROJECT")
            )
            if project_id:
                provider_kwargs["project_id"] = project_id
            else:
                self.console.print("[bold red]ERROR: No project ID specified for VertexAI. Set VERTEXAI_PROJECT in config or environment.[/bold red]")
                return provider, None, provider_kwargs
                
            # Handle VertexAI location from config or environment
            location = (
                self.config_vars.get("VERTEXAI_LOCATION")
                or self.config_vars.get("VERTEX_LOCATION")
                or os.environ.get("VERTEXAI_LOCATION")
                or os.environ.get("VERTEX_LOCATION")
            )
            if location:
                provider_kwargs["location"] = location
            else:
                self.console.print("[bold red]ERROR: No location specified for VertexAI. Set VERTEXAI_LOCATION in config or environment.[/bold red]")
                return provider, None, provider_kwargs
        elif provider.lower() == "groq":
            api_key = self.config_vars.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY")
        elif provider.lower() == "openai":
            api_key = self.config_vars.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        else:
            # Fallback to generic API key or anthropic key for backward compatibility
            api_key = self.api_key or os.environ.get("API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
            
        return provider, api_key, provider_kwargs
        
    def configure_model_settings(self, args: Any, provider: str) -> None:
        """Configure model and token settings based on provider.
        
        Args:
            args: Command line arguments
            provider: Provider name
        """
        # Set model based on provider-specific model configuration if not explicitly specified
        if not args.model:
            provider_lower = provider.lower()
            provider_upper = provider.upper()
            
            # Use provider-specific model setting
            if provider_lower == "anthropic":
                args.model = self.config_vars.get("ANTHROPIC_MODEL", get_default_model(provider_lower))
            elif provider_lower == "vertexai":
                args.model = self.config_vars.get("VERTEXAI_MODEL", get_default_model(provider_lower))
            elif provider_lower == "groq":
                args.model = self.config_vars.get("GROQ_MODEL", get_default_model(provider_lower))
            elif provider_lower == "openai":
                args.model = self.config_vars.get("OPENAI_MODEL", get_default_model(provider_lower))
            else:
                # For non-standard providers, use their specific config
                args.model = self.config_vars.get(f"{provider_upper}_MODEL")
                if not args.model:
                    raise ValueError(f"No model specified for provider {provider}. Add {provider_upper}_MODEL to config.")
        
        # Set max_tokens based on provider-specific config
        provider_lower = provider.lower()
        max_tokens_key = f"{provider.upper()}_MAX_TOKENS"
        
        if max_tokens_key in self.config_vars:
            args.max_tokens = int(self.config_vars.get(max_tokens_key))
        else:
            # Default to a reasonable value if not specified
            args.max_tokens = get_max_tokens(provider_lower)
        
    def get_permission_settings(self) -> Tuple[List[str], List[str], List[str]]:
        """Get permission settings from config file.
        
        Returns:
            Tuple containing:
            - List of always approved commands
            - List of always restricted commands
            - List of prohibited commands
        """
        # Parse command lists from config
        always_approved = parse_command_list(
            self.config_vars.get("ALWAYS_APPROVED_COMMANDS", "")
        )
        always_restricted = parse_command_list(
            self.config_vars.get("ALWAYS_RESTRICTED_COMMANDS", "")
        )
        prohibited = parse_command_list(
            self.config_vars.get("PROHIBITED_COMMANDS", "")
        )
        
        return always_approved, always_restricted, prohibited
        
    def update_config_provider(self, provider: str, model: Optional[str] = None) -> bool:
        """Update provider in config file.
        
        Args:
            provider: Provider name to set as default
            model: Optional model name to set as default for the provider
            
        Returns:
            True if config was updated, False otherwise
        """
        try:
            # Read existing config
            with open(CONFIG_PATH, "r") as f:
                lines = f.readlines()
                
            # Process each line, updating PROVIDER and model settings
            provider_updated = False
            model_updated = False
            updated_lines = []
            
            for line in lines:
                stripped = line.strip()
                
                # Update provider line
                if stripped.startswith("PROVIDER="):
                    updated_lines.append(f"PROVIDER={provider}\n")
                    provider_updated = True
                # Update model line for this provider
                elif model and stripped.startswith(f"{provider.upper()}_MODEL="):
                    updated_lines.append(f"{provider.upper()}_MODEL={model}\n")
                    model_updated = True
                else:
                    updated_lines.append(line)
                    
            # Add provider line if not found
            if not provider_updated:
                updated_lines.append(f"PROVIDER={provider}\n")
                
            # Add model line if not found and model provided
            if model and not model_updated:
                updated_lines.append(f"{provider.upper()}_MODEL={model}\n")
                
            # Write updated config
            with open(CONFIG_PATH, "w") as f:
                f.writelines(updated_lines)
                
            self.console.print(f"[green]Updated config file with provider: {provider}[/green]")
            if model:
                self.console.print(f"[green]Updated config file with model: {model}[/green]")
                
            return True
            
        except Exception as e:
            self.console.print(f"[yellow]Error updating config file: {str(e)}[/yellow]")
            return False