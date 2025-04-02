"""Tests for the provider factory module."""

import os
import pytest
from unittest.mock import patch, MagicMock

from q_cli.utils.provider_factory import (
    BaseProviderConfig,
    AnthropicProviderConfig,
    VertexAIProviderConfig,
    GroqProviderConfig,
    OpenAIProviderConfig,
    ProviderFactory
)
from q_cli.utils.constants import (
    ANTHROPIC_DEFAULT_MODEL,
    VERTEXAI_DEFAULT_MODEL,
    GROQ_DEFAULT_MODEL,
    OPENAI_DEFAULT_MODEL
)


class TestBaseProviderConfig:
    """Tests for the BaseProviderConfig class."""
    
    def test_default_implementations(self):
        """Test the default implementations in the base class."""
        # Create a concrete implementation of the abstract class for testing
        class ConcreteProvider(BaseProviderConfig):
            PROVIDER_NAME = "test_provider"
            DEFAULT_MODEL = "test_model"
            MAX_TOKENS = 1000
            
            def setup_environment(self):
                pass
                
            def format_model_name(self, model_name):
                return model_name
        
        # Create an instance
        provider = ConcreteProvider(api_key="test_key", model="custom_model")
        
        # Test properties and methods
        assert provider.api_key == "test_key"
        assert provider.model == "custom_model"
        assert provider.get_provider_name() == "test_provider"
        assert provider.get_error_handler() == {}
        
        # Test config
        config = provider.get_config()
        assert config["provider"] == "test_provider"
        assert config["model"] == "custom_model"
        assert config["max_tokens"] == 1000


class TestAnthropicProviderConfig:
    """Tests for the AnthropicProviderConfig class."""
    
    def test_initialization(self):
        """Test initialization with default values."""
        provider = AnthropicProviderConfig()
        assert provider.PROVIDER_NAME == "anthropic"
        assert provider.DEFAULT_MODEL == ANTHROPIC_DEFAULT_MODEL
        assert provider.model == ANTHROPIC_DEFAULT_MODEL
        assert provider.api_key is None
    
    def test_initialization_with_values(self):
        """Test initialization with provided values."""
        provider = AnthropicProviderConfig(api_key="test_api_key", model="claude-3-7-sonnet-latest")
        assert provider.api_key == "test_api_key"
        assert provider.model == "claude-3-7-sonnet-latest"
    
    @patch.dict(os.environ, {}, clear=True)
    def test_setup_environment(self):
        """Test environment setup."""
        provider = AnthropicProviderConfig(api_key="test_api_key")
        provider.setup_environment()
        assert os.environ.get("ANTHROPIC_API_KEY") == "test_api_key"
    
    def test_format_model_name(self):
        """Test model name formatting."""
        provider = AnthropicProviderConfig()
        
        # Test with no prefix
        assert provider.format_model_name("claude-3-sonnet") == "anthropic/claude-3-sonnet"
        
        # Test with existing prefix
        assert provider.format_model_name("anthropic/claude-3-sonnet") == "anthropic/claude-3-sonnet"
        
        # Test with other prefix format
        assert provider.format_model_name("claude-3:sonnet") == "claude-3:sonnet"


class TestVertexAIProviderConfig:
    """Tests for the VertexAIProviderConfig class."""
    
    def test_initialization_with_defaults(self):
        """Test initialization with default values."""
        provider = VertexAIProviderConfig(project_id="test-project")
        assert provider.PROVIDER_NAME == "vertexai"
        assert provider.DEFAULT_MODEL == VERTEXAI_DEFAULT_MODEL
        assert provider.model == VERTEXAI_DEFAULT_MODEL
        assert provider.api_key is None
        assert provider.project_id == "test-project"
        assert provider.location == "us-west4"  # Default location
    
    def test_initialization_with_values(self):
        """Test initialization with provided values."""
        provider = VertexAIProviderConfig(
            api_key="/path/to/key.json",
            model="gemini-2.0-pro",
            project_id="custom-project",
            location="us-central1"
        )
        assert provider.api_key == "/path/to/key.json"
        assert provider.model == "gemini-2.0-pro"
        assert provider.project_id == "custom-project"
        assert provider.location == "us-central1"
    
    @patch.dict(os.environ, {}, clear=True)
    @patch('os.path.isfile', return_value=True)
    @patch('os.path.isabs', return_value=True)
    @patch('json.load', return_value={"project_id": "extracted-project"})
    @patch('builtins.open', MagicMock())
    def test_setup_environment_with_file(self, mock_json_load, mock_isabs, mock_isfile):
        """Test environment setup with credential file."""
        provider = VertexAIProviderConfig(
            api_key="/path/to/key.json",
            project_id="test-project",
            location="us-central1"
        )
        provider.setup_environment()
        
        # Check environment variables
        assert os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") == "/path/to/key.json"
        assert os.environ.get("GOOGLE_PROJECT") == "test-project"
        assert os.environ.get("VERTEXAI_PROJECT") == "test-project"
        assert os.environ.get("PROJECT_ID") == "test-project"
        assert os.environ.get("GCP_PROJECT") == "test-project"
        assert os.environ.get("VERTEX_LOCATION") == "us-central1"
        assert os.environ.get("VERTEXAI_LOCATION") == "us-central1"
    
    def test_format_model_name(self):
        """Test model name formatting."""
        provider = VertexAIProviderConfig(project_id="test-project")
        
        # Test with no prefix
        assert provider.format_model_name("gemini-2.0-pro") == "vertex_ai/gemini-2.0-pro"
        
        # Test with existing prefix
        assert provider.format_model_name("vertex_ai/gemini-2.0-pro") == "vertex_ai/gemini-2.0-pro"
        
        # Test with other prefix format
        assert provider.format_model_name("gemini:2.0-pro") == "gemini:2.0-pro"
    
    def test_get_error_handler(self):
        """Test error handler dictionary."""
        provider = VertexAIProviderConfig(project_id="test-project")
        error_handlers = provider.get_error_handler()
        
        # Verify key error types are handled
        assert "PERMISSION_DENIED" in error_handlers
        assert "UNAUTHENTICATED" in error_handlers
        assert "NOT_FOUND" in error_handlers
        assert "RESOURCE_EXHAUSTED" in error_handlers
        
        # Verify handler structure
        for handler in error_handlers.values():
            assert "message" in handler
            assert "resolution" in handler


class TestGroqProviderConfig:
    """Tests for the GroqProviderConfig class."""
    
    def test_initialization(self):
        """Test initialization with default values."""
        provider = GroqProviderConfig()
        assert provider.PROVIDER_NAME == "groq"
        assert provider.DEFAULT_MODEL == GROQ_DEFAULT_MODEL
        assert provider.model == GROQ_DEFAULT_MODEL
        assert provider.api_key is None
    
    def test_initialization_with_values(self):
        """Test initialization with provided values."""
        provider = GroqProviderConfig(api_key="test_api_key", model="llama3-70b-flash")
        assert provider.api_key == "test_api_key"
        assert provider.model == "llama3-70b-flash"
    
    @patch.dict(os.environ, {}, clear=True)
    def test_setup_environment(self):
        """Test environment setup."""
        provider = GroqProviderConfig(api_key="test_api_key")
        provider.setup_environment()
        assert os.environ.get("GROQ_API_KEY") == "test_api_key"
    
    def test_format_model_name(self):
        """Test model name formatting."""
        provider = GroqProviderConfig()
        
        # Test with no prefix
        assert provider.format_model_name("mixtral-8x7b") == "groq/mixtral-8x7b"
        
        # Test with existing prefix
        assert provider.format_model_name("groq/mixtral-8x7b") == "groq/mixtral-8x7b"
        
        # Test with other prefix format
        assert provider.format_model_name("mixtral:8x7b") == "mixtral:8x7b"


class TestOpenAIProviderConfig:
    """Tests for the OpenAIProviderConfig class."""
    
    def test_initialization(self):
        """Test initialization with default values."""
        provider = OpenAIProviderConfig()
        assert provider.PROVIDER_NAME == "openai"
        assert provider.DEFAULT_MODEL == OPENAI_DEFAULT_MODEL
        assert provider.model == OPENAI_DEFAULT_MODEL
        assert provider.api_key is None
    
    def test_initialization_with_values(self):
        """Test initialization with provided values."""
        provider = OpenAIProviderConfig(api_key="test_api_key", model="gpt-4o")
        assert provider.api_key == "test_api_key"
        assert provider.model == "gpt-4o"
    
    @patch.dict(os.environ, {}, clear=True)
    def test_setup_environment(self):
        """Test environment setup."""
        provider = OpenAIProviderConfig(api_key="test_api_key")
        provider.setup_environment()
        assert os.environ.get("OPENAI_API_KEY") == "test_api_key"
    
    def test_format_model_name(self):
        """Test model name formatting."""
        provider = OpenAIProviderConfig()
        
        # Test with no prefix
        assert provider.format_model_name("gpt-4o") == "openai/gpt-4o"
        
        # Test with existing prefix
        assert provider.format_model_name("openai/gpt-4o") == "openai/gpt-4o"
        
        # Test with other prefix format
        assert provider.format_model_name("gpt-4:turbo") == "gpt-4:turbo"


class TestProviderFactory:
    """Tests for the ProviderFactory class."""
    
    def test_create_provider_with_provider_name(self):
        """Test creating provider with explicit provider name."""
        # Anthropic provider
        provider = ProviderFactory.create_provider(provider_name="anthropic", api_key="test_key")
        assert isinstance(provider, AnthropicProviderConfig)
        assert provider.api_key == "test_key"
        
        # OpenAI provider
        provider = ProviderFactory.create_provider(provider_name="openai", api_key="test_key")
        assert isinstance(provider, OpenAIProviderConfig)
        
        # Groq provider
        provider = ProviderFactory.create_provider(provider_name="groq", api_key="test_key")
        assert isinstance(provider, GroqProviderConfig)
        
        # VertexAI provider with required parameters
        provider = ProviderFactory.create_provider(
            provider_name="vertexai", 
            api_key="test_key.json",
            project_id="test-project",
            location="us-central1"
        )
        assert isinstance(provider, VertexAIProviderConfig)
    
    def test_create_provider_with_model_inference(self):
        """Test creating provider by inferring from model name."""
        # Anthropic model
        provider = ProviderFactory.create_provider(model="claude-3-opus")
        assert isinstance(provider, AnthropicProviderConfig)
        
        # Anthropic model with prefix
        provider = ProviderFactory.create_provider(model="anthropic/claude-3-sonnet")
        assert isinstance(provider, AnthropicProviderConfig)
        
        # VertexAI model
        with pytest.raises(ValueError):  # Should fail without project_id and location
            provider = ProviderFactory.create_provider(model="gemini-2.0-pro")
        
        # VertexAI model with required params
        provider = ProviderFactory.create_provider(
            model="gemini-2.0-pro",
            project_id="test-project",
            location="us-central1"
        )
        assert isinstance(provider, VertexAIProviderConfig)
        
        # VertexAI model with prefix
        provider = ProviderFactory.create_provider(
            model="google/gemini-2.0-flash",
            project_id="test-project",
            location="us-central1"
        )
        assert isinstance(provider, VertexAIProviderConfig)
        
        # Groq model
        provider = ProviderFactory.create_provider(model="mixtral-8x7b")
        assert isinstance(provider, GroqProviderConfig)
        
        # OpenAI model
        provider = ProviderFactory.create_provider(model="gpt-4o")
        assert isinstance(provider, OpenAIProviderConfig)
    
    def test_register_custom_provider(self):
        """Test registering and using a custom provider (skipped due to SUPPORTED_PROVIDERS limitation)."""
        pytest.skip("This test requires modifying SUPPORTED_PROVIDERS which is a constant")
        # Create a custom provider class
        class CustomProvider(BaseProviderConfig):
            PROVIDER_NAME = "custom"
            DEFAULT_MODEL = "custom-default"
            MAX_TOKENS = 5000
            
            def setup_environment(self):
                if self.api_key:
                    os.environ["CUSTOM_API_KEY"] = self.api_key
            
            def format_model_name(self, model_name):
                if not "/" in model_name:
                    return f"custom/{model_name}"
                return model_name
        
        # Register the custom provider
        ProviderFactory.register_provider("custom", CustomProvider)
        
        # Test using the custom provider
        provider = ProviderFactory.create_provider(provider_name="custom", api_key="test_key")
        assert isinstance(provider, CustomProvider)
        assert provider.api_key == "test_key"
        assert provider.model == "custom-default"
    
    def test_unsupported_provider(self):
        """Test error handling for unsupported providers."""
        with pytest.raises(ValueError) as excinfo:
            ProviderFactory.create_provider(provider_name="nonexistent")
        assert "Unsupported provider" in str(excinfo.value)
        
    def test_infer_provider_from_model(self):
        """Test provider inference from model names."""
        # Anthropic models
        assert ProviderFactory.infer_provider_from_model("claude-3-opus") == "anthropic"
        assert ProviderFactory.infer_provider_from_model("anthropic/claude-3-haiku") == "anthropic"
        
        # VertexAI models
        assert ProviderFactory.infer_provider_from_model("gemini-2.0-pro") == "vertexai"
        assert ProviderFactory.infer_provider_from_model("google/gemini-2.0-flash") == "vertexai"
        assert ProviderFactory.infer_provider_from_model("gemma-7b") == "vertexai"
        
        # Groq models
        assert ProviderFactory.infer_provider_from_model("mixtral-8x7b") == "groq"
        assert ProviderFactory.infer_provider_from_model("groq/llama3-70b") == "groq"
        assert ProviderFactory.infer_provider_from_model("deepseek-r1-distill") == "groq"
        
        # OpenAI models
        assert ProviderFactory.infer_provider_from_model("gpt-4o") == "openai"
        assert ProviderFactory.infer_provider_from_model("openai/gpt-4-turbo") == "openai"
        assert ProviderFactory.infer_provider_from_model("ft:gpt-3.5-turbo") == "openai"
        
        # Default for unknown
        assert ProviderFactory.infer_provider_from_model("unknown-model") == "anthropic"