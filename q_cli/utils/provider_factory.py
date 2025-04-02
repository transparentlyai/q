"""Provider-specific configuration factory for q_cli."""

import os
from typing import Dict, Any, Optional, List, Tuple, Type
import json
from abc import ABC, abstractmethod

from q_cli.utils.constants import (
    get_debug,
    DEFAULT_PROVIDER,
    SUPPORTED_PROVIDERS,
    ANTHROPIC_DEFAULT_MODEL,
    VERTEXAI_DEFAULT_MODEL,
    GROQ_DEFAULT_MODEL,
    OPENAI_DEFAULT_MODEL,
    ANTHROPIC_MAX_TOKENS,
    VERTEXAI_MAX_TOKENS,
    GROQ_MAX_TOKENS,
    OPENAI_MAX_TOKENS
)


class BaseProviderConfig(ABC):
    """Base class for provider-specific configurations."""
    
    # Class variables with provider information
    PROVIDER_NAME: str
    DEFAULT_MODEL: str
    MAX_TOKENS: int
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize provider configuration.
        
        Args:
            api_key: API key for the provider
            model: Model name to use (defaults to provider's default)
        """
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        
    @abstractmethod
    def setup_environment(self) -> None:
        """Set up the environment variables required by this provider."""
        pass
    
    @abstractmethod
    def format_model_name(self, model_name: str) -> str:
        """Format the model name according to provider conventions."""
        pass
    
    def get_provider_name(self) -> str:
        """Return the provider name."""
        return self.PROVIDER_NAME
    
    def get_error_handler(self) -> Dict[str, Any]:
        """Return provider-specific error handling mappings."""
        return {}
    
    def get_config(self) -> Dict[str, Any]:
        """Return the provider configuration as a dictionary."""
        return {
            "provider": self.PROVIDER_NAME,
            "model": self.model,
            "max_tokens": self.MAX_TOKENS,
        }


class AnthropicProviderConfig(BaseProviderConfig):
    """Anthropic provider configuration."""
    
    PROVIDER_NAME = "anthropic"
    DEFAULT_MODEL = ANTHROPIC_DEFAULT_MODEL
    MAX_TOKENS = ANTHROPIC_MAX_TOKENS
    
    def setup_environment(self) -> None:
        """Set up Anthropic environment variables."""
        if self.api_key:
            os.environ["ANTHROPIC_API_KEY"] = self.api_key
    
    def format_model_name(self, model_name: str) -> str:
        """Format model name with anthropic/ prefix if not present."""
        # Use the centralized helper function for consistent formatting
        from q_cli.config.providers import format_model_for_litellm
        return format_model_for_litellm("anthropic", model_name)


class VertexAIProviderConfig(BaseProviderConfig):
    """Google VertexAI provider configuration."""
    
    PROVIDER_NAME = "vertexai"
    DEFAULT_MODEL = VERTEXAI_DEFAULT_MODEL
    MAX_TOKENS = VERTEXAI_MAX_TOKENS
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None,
                 project_id: Optional[str] = None, location: Optional[str] = None):
        """
        Initialize VertexAI provider configuration.
        
        Args:
            api_key: Path to service account JSON file, API key, or "ADC" to use Application Default Credentials
            model: Model name to use
            project_id: GCP project ID
            location: GCP region (e.g., "us-west4")
        """
        super().__init__(api_key, model)
        self.project_id = project_id
        self.location = location or "us-west4"  # Default location
    
    def setup_environment(self) -> None:
        """Set up VertexAI environment variables."""
        if not self.api_key:
            if get_debug():
                print("WARNING: No API key provided for VertexAI")
            return
            
        # Handle Application Default Credentials
        if self.api_key.upper() == "ADC":
            if get_debug():
                print("Using Application Default Credentials (ADC) for VertexAI")
            # ADC uses the credentials configured in the environment
            # No need to set GOOGLE_APPLICATION_CREDENTIALS
        # Handle service account JSON file
        elif os.path.isfile(self.api_key):
            # Set credentials path
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.api_key
            
            # Convert to absolute path if not already
            if not os.path.isabs(self.api_key):
                abs_path = os.path.abspath(self.api_key)
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = abs_path
                
            if get_debug():
                print(f"Set GOOGLE_APPLICATION_CREDENTIALS to {os.environ['GOOGLE_APPLICATION_CREDENTIALS']}")
                
            # Try to extract project ID from credentials file
            self._extract_project_id_from_credentials()
        else:
            # Fallback to using as a direct key (though not standard for VertexAI)
            print(f"WARNING: API key '{self.api_key}' is not a file path. VertexAI typically expects a JSON service account file.")
            os.environ["VERTEXAI_API_KEY"] = self.api_key
            if get_debug():
                print(f"Using direct API key for VertexAI (not recommended)")
        
        # Set up project ID
        self._setup_project_id()
        
        # Set up location
        self._setup_location()
    
    def _extract_project_id_from_credentials(self) -> Optional[str]:
        """Extract project ID from credentials file."""
        if not self.project_id and self.api_key and os.path.isfile(self.api_key):
            try:
                import json
                with open(self.api_key, 'r') as f:
                    creds_data = json.load(f)
                    if 'project_id' in creds_data:
                        self.project_id = creds_data['project_id']
                        if get_debug():
                            print(f"Extracted project_id from credentials file: {self.project_id}")
                        return self.project_id
            except Exception as e:
                if get_debug():
                    print(f"Error extracting project_id from credentials file: {str(e)}")
        
        # Try to extract from filename
        if not self.project_id and self.api_key and os.path.isfile(self.api_key):
            try:
                filename = os.path.basename(self.api_key)
                if "-" in filename and (filename.endswith(".json") or filename.endswith(".JSON")):
                    possible_project = filename.split(".json")[0].split(".JSON")[0]
                    if get_debug():
                        print(f"Possible project ID from filename: {possible_project}")
                    self.project_id = possible_project
                    return self.project_id
            except Exception as e:
                if get_debug():
                    print(f"Error extracting project_id from filename: {str(e)}")
        
        # Special case handling
        if not self.project_id and self.api_key:
            # If celeritas-eng-dev is in the service account path, use it
            if "celeritas-eng-dev" in self.api_key:
                self.project_id = "celeritas-eng-dev"
                if get_debug():
                    print(f"Using project ID from path: {self.project_id}")
                return self.project_id
                
            # Special case for q-for-mauro.json
            if "q-for-mauro.json" in str(self.api_key):
                self.project_id = "celeritas-eng-dev"
                if get_debug():
                    print(f"Using hardcoded project ID for q-for-mauro.json: {self.project_id}")
                return self.project_id
        
        return None
    
    def _setup_project_id(self) -> None:
        """Set up project ID environment variables."""
        # First try to get from existing environment variables
        if not self.project_id:
            for env_var in ["VERTEXAI_PROJECT", "VERTEX_PROJECT", "GOOGLE_PROJECT", "PROJECT_ID", "GCP_PROJECT"]:
                if env_var in os.environ and os.environ[env_var].strip():
                    self.project_id = os.environ[env_var].strip()
                    if get_debug():
                        print(f"Found project ID in {env_var}: {self.project_id}")
                    break
        
        # Set project ID in all expected environment variables if found
        if self.project_id:
            for env_var in ["GOOGLE_PROJECT", "VERTEXAI_PROJECT", "PROJECT_ID", "GCP_PROJECT"]:
                os.environ[env_var] = self.project_id
            if get_debug():
                print(f"Set all project environment variables to: {self.project_id}")
        else:
            print("ERROR: VERTEXAI_PROJECT not set in environment (required for VertexAI)")
            print("Please set VERTEXAI_PROJECT in your config file or environment variables")
            
            if get_debug():
                print(f"API key: {self.api_key}")
                print(f"Current environment variables:")
                for key in sorted(os.environ.keys()):
                    if "PROJECT" in key or "VERTEX" in key or "GOOGLE" in key:
                        print(f"  {key}={os.environ[key]}")
                print("Config file settings should be in ~/.config/q.conf")
    
    def _setup_location(self) -> None:
        """Set up location environment variables."""
        # Try to find location in environment variables first
        if not self.location:
            for env_var in ["VERTEXAI_LOCATION", "VERTEX_LOCATION", "GOOGLE_LOCATION", "LOCATION_ID", "GCP_LOCATION"]:
                if env_var in os.environ and os.environ[env_var].strip():
                    self.location = os.environ[env_var].strip()
                    if get_debug():
                        print(f"Found location in {env_var}: {self.location}")
                    break
        
        # Set the location in all environment variables
        if self.location:
            for env_var in ["VERTEX_LOCATION", "VERTEXAI_LOCATION", "LOCATION_ID", "GCP_LOCATION", "GOOGLE_LOCATION"]:
                os.environ[env_var] = self.location
                
            if get_debug():
                print(f"Set all location environment variables to: {self.location}")
    
    def format_model_name(self, model_name: str) -> str:
        """Format model name with vertex_ai/ prefix if not present for LiteLLM compatibility."""
        # Use the centralized helper function for consistent formatting
        from q_cli.config.providers import format_model_for_litellm
        return format_model_for_litellm("vertexai", model_name)
    
    def get_error_handler(self) -> Dict[str, Any]:
        """Return VertexAI-specific error handling mappings."""
        return {
            # Permission errors
            "PERMISSION_DENIED": {
                "message": (
                    "VertexAI permission denied error. This typically means:\n"
                    "1. The service account doesn't have sufficient permissions\n"
                    "2. Required IAM role: 'roles/aiplatform.user' or 'aiplatform.admin'\n" 
                    "3. Make sure the Vertex AI API is enabled in your project\n"
                    "4. If using ADC, ensure your default credentials have proper permissions"
                ),
                "resolution": "Check service account permissions and API enablement."
            },
            # Authentication errors
            "UNAUTHENTICATED": {
                "message": (
                    "VertexAI authentication error. Please check:\n"
                    "1. Your service account JSON file is valid\n"
                    "2. Project ID is correct\n"
                    "3. Location is correct\n"
                    "4. If using ADC, ensure you're properly authenticated (run 'gcloud auth application-default login')"
                ),
                "resolution": "Verify your credentials and project settings."
            },
            # Not found errors
            "NOT_FOUND": {
                "message": (
                    "VertexAI model error: Model may not exist or isn't accessible. Please check:\n"
                    "1. The model name is correct (try alternatives like 'gemini-2.0-flash-001')\n"
                    "2. The model is available in your project's region\n"
                    "3. Your service account has access to this model"
                ),
                "resolution": "Verify model name and availability."
            },
            # Quota errors
            "RESOURCE_EXHAUSTED": {
                "message": (
                    "VertexAI quota exceeded. Please check:\n"
                    "1. Your project has sufficient quota for VertexAI API calls\n"
                    "2. Try again after a brief waiting period\n"
                    "3. Consider requesting higher quotas in Google Cloud Console"
                ),
                "resolution": "Wait and retry, or request higher quota."
            }
        }
    
    def get_config(self) -> Dict[str, Any]:
        """Return the provider configuration as a dictionary."""
        config = super().get_config()
        config.update({
            "project_id": self.project_id,
            "location": self.location,
        })
        return config


class GroqProviderConfig(BaseProviderConfig):
    """Groq provider configuration."""
    
    PROVIDER_NAME = "groq"
    DEFAULT_MODEL = GROQ_DEFAULT_MODEL
    MAX_TOKENS = GROQ_MAX_TOKENS
    
    def setup_environment(self) -> None:
        """Set up Groq environment variables."""
        if self.api_key:
            os.environ["GROQ_API_KEY"] = self.api_key
    
    def format_model_name(self, model_name: str) -> str:
        """Format model name with groq/ prefix if not present."""
        # Use the centralized helper function for consistent formatting
        from q_cli.config.providers import format_model_for_litellm
        return format_model_for_litellm("groq", model_name)


class OpenAIProviderConfig(BaseProviderConfig):
    """OpenAI provider configuration."""
    
    PROVIDER_NAME = "openai"
    DEFAULT_MODEL = OPENAI_DEFAULT_MODEL
    MAX_TOKENS = OPENAI_MAX_TOKENS
    
    def setup_environment(self) -> None:
        """Set up OpenAI environment variables."""
        if self.api_key:
            os.environ["OPENAI_API_KEY"] = self.api_key
    
    def format_model_name(self, model_name: str) -> str:
        """Format model name with openai/ prefix if not present."""
        # Use the centralized helper function for consistent formatting
        from q_cli.config.providers import format_model_for_litellm
        return format_model_for_litellm("openai", model_name)


class ProviderFactory:
    """Factory for creating and managing provider configurations."""
    
    # Registry of provider classes
    _provider_registry: Dict[str, Type[BaseProviderConfig]] = {
        "anthropic": AnthropicProviderConfig,
        "vertexai": VertexAIProviderConfig,
        "groq": GroqProviderConfig,
        "openai": OpenAIProviderConfig,
    }
    
    @classmethod
    def register_provider(cls, provider_name: str, provider_class: Type[BaseProviderConfig]) -> None:
        """
        Register a new provider configuration class.
        
        Args:
            provider_name: Name of the provider
            provider_class: Provider configuration class
        """
        cls._provider_registry[provider_name.lower()] = provider_class
    
    @classmethod
    def create_provider(cls, provider_name: Optional[str] = None, 
                        model: Optional[str] = None,
                        api_key: Optional[str] = None,
                        **kwargs) -> BaseProviderConfig:
        """
        Create a provider configuration based on provider name or model.
        
        Args:
            provider_name: Name of the provider
            model: Model name (used to infer provider if provider_name not provided)
            api_key: API key for the provider
            **kwargs: Additional provider-specific arguments
        
        Returns:
            Provider configuration instance
        
        Raises:
            ValueError: If provider is not supported or configuration is invalid
        """
        # If provider not specified, infer from model name
        if not provider_name and model:
            provider_name = cls.infer_provider_from_model(model)
        
        # If still not specified, use default
        provider_name = provider_name or DEFAULT_PROVIDER
        provider_name = provider_name.lower()
        
        # Verify provider is supported
        if provider_name not in cls._provider_registry:
            supported = ", ".join(sorted(cls._provider_registry.keys()))
            raise ValueError(f"Unsupported provider: {provider_name}. Supported providers: {supported}")
        
        # Verify provider is in the allowed list
        if provider_name not in SUPPORTED_PROVIDERS:
            allowed = ", ".join(sorted(SUPPORTED_PROVIDERS))
            raise ValueError(f"Provider '{provider_name}' is not in the allowed providers list: {allowed}")
        
        # Create provider configuration
        provider_class = cls._provider_registry[provider_name]
        
        # Special handling for VertexAI which has additional parameters
        if provider_name == "vertexai":
            # Check for required additional parameters for VertexAI
            project_id = kwargs.get("project_id")
            location = kwargs.get("location")
            
            if not project_id:
                raise ValueError("VertexAI provider requires a project_id")
                
            if not location:
                raise ValueError("VertexAI provider requires a location")
                
            return provider_class(
                api_key=api_key,
                model=model,
                project_id=project_id,
                location=location
            )
        
        # Standard provider configuration
        return provider_class(api_key=api_key, model=model)
    
    @classmethod
    def infer_provider_from_model(cls, model: str) -> str:
        """
        Infer provider from model name.
        
        Args:
            model: Model name
        
        Returns:
            Inferred provider name
        """
        if not model:
            return DEFAULT_PROVIDER
            
        model_lower = model.lower()
        
        # Check for provider prefixes in model name
        if "anthropic/" in model_lower:
            return "anthropic"
        elif "google/" in model_lower or "vertex" in model_lower:
            return "vertexai"
        elif "groq/" in model_lower:
            return "groq"
        elif "openai/" in model_lower:
            return "openai"
        
        # Check for model name patterns
        if "claude" in model_lower:
            return "anthropic"
        elif any(name in model_lower for name in ["gemini", "gecko", "gemma", "palm"]):
            return "vertexai"
        elif any(name in model_lower for name in ["deepseek", "llama", "mixtral", "falcon"]):
            return "groq"
        elif any(name in model_lower for name in ["gpt", "ft:gpt", "text-davinci", "dall-e"]):
            return "openai"
        
        # Default fallback
        return DEFAULT_PROVIDER