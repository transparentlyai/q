"""Tests for the LLM client module."""

import pytest
from unittest.mock import patch, MagicMock, ANY
import litellm

from q_cli.utils.client import LLMClient
from q_cli.utils.provider_factory import AnthropicProviderConfig


class TestLLMClient:
    """Tests for the LLMClient class."""
    
    @patch('q_cli.utils.provider_factory.ProviderFactory.create_provider')
    def test_initialization_with_defaults(self, mock_create_provider):
        """Test client initialization with default values."""
        # Setup provider mock
        mock_provider = MagicMock(spec=AnthropicProviderConfig)
        mock_provider.get_provider_name.return_value = "anthropic"
        mock_provider.format_model_name.return_value = "anthropic/claude-3-sonnet-latest"
        mock_create_provider.return_value = mock_provider
        
        # Create client
        client = LLMClient()
        
        # Verify provider creation
        mock_create_provider.assert_called_once()
        assert client.provider == "anthropic"
        assert client.model == "anthropic/claude-3-sonnet-latest"
    
    @patch('q_cli.utils.provider_factory.ProviderFactory.create_provider')
    def test_initialization_with_custom_values(self, mock_create_provider):
        """Test client initialization with custom values."""
        # Setup provider mock
        mock_provider = MagicMock(spec=AnthropicProviderConfig)
        mock_provider.get_provider_name.return_value = "anthropic"
        mock_provider.format_model_name.return_value = "anthropic/claude-3-7-sonnet-latest"
        mock_create_provider.return_value = mock_provider
        
        # Create client with custom values
        client = LLMClient(
            api_key="test_api_key",
            model="claude-3-7-sonnet-latest",
            provider="anthropic"
        )
        
        # Verify provider creation
        mock_create_provider.assert_called_once_with(
            provider_name="anthropic",
            model="claude-3-7-sonnet-latest",
            api_key="test_api_key"
        )
        assert client.provider == "anthropic"
        assert client.model == "anthropic/claude-3-7-sonnet-latest"
    
    @patch('q_cli.utils.provider_factory.ProviderFactory.create_provider')
    @patch('litellm.completion')
    def test_messages_create(self, mock_completion, mock_create_provider):
        """Test the messages_create method."""
        # Setup provider mock
        mock_provider = MagicMock(spec=AnthropicProviderConfig)
        mock_provider.get_provider_name.return_value = "anthropic"
        mock_provider.format_model_name.return_value = "anthropic/claude-3-sonnet-latest"
        mock_provider.MAX_TOKENS = 8192
        mock_provider.get_config.return_value = {
            "provider": "anthropic",
            "model": "claude-3-sonnet-latest",
            "max_tokens": 8192
        }
        mock_provider.get_error_handler.return_value = {}
        mock_create_provider.return_value = mock_provider
        
        # Setup completion mock
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].finish_reason = "stop"
        mock_completion.return_value = mock_response
        
        # Create client and call messages_create
        client = LLMClient(model="claude-3-sonnet-latest")
        response = client.messages_create(
            model="anthropic/claude-3-sonnet-latest",
            max_tokens=1000,
            temperature=0.7,
            system="You are a helpful assistant",
            messages=[{"role": "user", "content": "Hello"}]
        )
        
        # Verify litellm was called correctly
        mock_completion.assert_called_once_with(
            model="anthropic/claude-3-sonnet-latest",
            messages=ANY,  # We'll verify the structure separately
            max_tokens=1000,
            temperature=0.7,
            stream=False
        )
        
        # Verify messages were transformed correctly
        messages_arg = mock_completion.call_args[1]['messages']
        assert len(messages_arg) == 2
        assert messages_arg[0]['role'] == 'system'
        assert messages_arg[0]['content'] == 'You are a helpful assistant'
        assert messages_arg[1]['role'] == 'user'
        assert messages_arg[1]['content'] == 'Hello'
        
        # Verify response was transformed correctly
        assert hasattr(response, 'choices')
        assert len(response.choices) == 1
        assert response.choices[0]['message']['content'] == 'Test response'
        assert response.choices[0]['finish_reason'] == 'stop'
    
    @patch('q_cli.utils.provider_factory.ProviderFactory.create_provider')
    def test_transform_messages_simple(self, mock_create_provider):
        """Test simple message transformation."""
        # Setup provider mock
        mock_provider = MagicMock(spec=AnthropicProviderConfig)
        mock_provider.get_provider_name.return_value = "anthropic"
        mock_provider.format_model_name.return_value = "anthropic/claude-3-sonnet-latest"
        mock_create_provider.return_value = mock_provider
        
        # Create client
        client = LLMClient()
        
        # Test basic message transformation
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"}
        ]
        
        result = client._transform_messages(messages, system="You are a helpful assistant")
        
        # Verify structure
        assert len(result) == 4
        assert result[0]['role'] == 'system'
        assert result[0]['content'] == 'You are a helpful assistant'
        assert result[1]['role'] == 'user'
        assert result[1]['content'] == 'Hello'
        assert result[2]['role'] == 'assistant'
        assert result[2]['content'] == 'Hi there!'
        assert result[3]['role'] == 'user'
        assert result[3]['content'] == 'How are you?'
    
    @patch('q_cli.utils.provider_factory.ProviderFactory.create_provider')
    def test_transform_messages_multimodal(self, mock_create_provider):
        """Test multimodal message transformation."""
        # Setup provider mock
        mock_provider = MagicMock(spec=AnthropicProviderConfig)
        mock_provider.get_provider_name.return_value = "anthropic"
        mock_provider.format_model_name.return_value = "anthropic/claude-3-sonnet-latest"
        mock_create_provider.return_value = mock_provider
        
        # Create client
        client = LLMClient()
        
        # Test multimodal message transformation
        messages = [
            {
                "role": "user", 
                "content": [
                    {"type": "text", "text": "What's in this image?"},
                    {
                        "type": "image", 
                        "source": {
                            "data": "base64data", 
                            "media_type": "image/jpeg"
                        }
                    }
                ]
            }
        ]
        
        result = client._transform_messages(messages)
        
        # Verify structure
        assert len(result) == 1
        assert result[0]['role'] == 'user'
        assert isinstance(result[0]['content'], list)
        assert len(result[0]['content']) == 2
        assert result[0]['content'][0]['type'] == 'text'
        assert result[0]['content'][0]['text'] == "What's in this image?"
        assert result[0]['content'][1]['type'] == 'image_url'
        assert 'data:image/jpeg;base64,base64data' in result[0]['content'][1]['image_url']['url']
    
    @patch('q_cli.utils.provider_factory.ProviderFactory.create_provider')
    @patch('litellm.completion')
    def test_error_handling(self, mock_completion, mock_create_provider):
        """Test error handling in messages_create."""
        # Setup provider mock
        mock_provider = MagicMock(spec=AnthropicProviderConfig)
        mock_provider.get_provider_name.return_value = "anthropic"
        mock_provider.format_model_name.return_value = "anthropic/claude-3-sonnet-latest"
        mock_provider.MAX_TOKENS = 8192
        mock_provider.get_error_handler.return_value = {
            "RATE_LIMIT": {
                "message": "Rate limit exceeded",
                "resolution": "Wait and retry"
            }
        }
        mock_create_provider.return_value = mock_provider
        
        # Setup error
        mock_completion.side_effect = litellm.exceptions.RateLimitError(
            message="RATE_LIMIT: Too many requests",
            model="claude-3-sonnet-latest",
            llm_provider="anthropic"
        )
        
        # Create client
        client = LLMClient()
        
        # Test error handling
        with pytest.raises(litellm.exceptions.RateLimitError) as excinfo:
            client.messages_create(
                model="anthropic/claude-3-sonnet-latest",
                max_tokens=1000,
                temperature=0.7,
                system="You are a helpful assistant",
                messages=[{"role": "user", "content": "Hello"}]
            )
        
        assert "RATE_LIMIT" in str(excinfo.value)