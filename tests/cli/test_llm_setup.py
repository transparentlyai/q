"""Tests for the LLM setup module."""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

from q_cli.cli.llm_setup import (
    setup_api_credentials,
    validate_model_for_provider,
    initialize_llm_client
)


class TestLLMSetup:
    """Tests for LLM setup functionality."""

    def test_validate_model_for_provider_valid(self, mock_console):
        """Test validating a valid model for a provider."""
        with patch('q_cli.cli.llm_setup.is_valid_model_for_provider', return_value=True):
            result = validate_model_for_provider('claude-3-5-sonnet', 'anthropic', mock_console)
            assert result is True
            mock_console.print.assert_not_called()

    def test_validate_model_for_provider_invalid(self, mock_console):
        """Test validating an invalid model for a provider."""
        with patch('q_cli.cli.llm_setup.is_valid_model_for_provider', return_value=False):
            result = validate_model_for_provider('invalid-model', 'anthropic', mock_console)
            assert result is False
            mock_console.print.assert_called_once()
            assert "Warning" in mock_console.print.call_args[0][0]

    def test_initialize_llm_client_success(self, mock_console):
        """Test initializing an LLM client successfully."""
        # Create mock args
        args = MagicMock()
        args.model = 'claude-3-5-sonnet'
        args.provider_kwargs = {}
        
        # Mock the LLMClient class
        mock_client = MagicMock()
        
        with patch('q_cli.cli.llm_setup.validate_model_for_provider', return_value=True):
            with patch('q_cli.utils.client.LLMClient', return_value=mock_client):
                with patch('q_cli.cli.llm_setup.get_debug', return_value=False):
                    client = initialize_llm_client('test_api_key', args, 'anthropic', mock_console)
                    
                    # Verify the client was initialized with the correct arguments
                    assert client == mock_client

    def test_initialize_llm_client_error(self, mock_console):
        """Test initializing an LLM client with an error."""
        # Create mock args
        args = MagicMock()
        args.model = 'claude-3-5-sonnet'
        args.provider_kwargs = {}
        
        # Mock LLMClient to raise an exception
        with patch('q_cli.cli.llm_setup.validate_model_for_provider', return_value=True):
            with patch('q_cli.utils.client.LLMClient', side_effect=Exception('Test error')):
                with pytest.raises(Exception) as excinfo:
                    initialize_llm_client('test_api_key', args, 'anthropic', mock_console)
                
                assert 'Test error' in str(excinfo.value)
                # Verify error message was printed
                assert mock_console.print.call_count >= 1
                assert 'Error' in mock_console.print.call_args_list[0][0][0]

    def test_setup_api_credentials_args_override(self, mock_console, temp_env):
        """Test setup_api_credentials with args overriding config."""
        # Create mock args
        args = MagicMock()
        args.provider = 'anthropic'
        args.api_key = 'arg_api_key'
        
        # Create config vars
        config_vars = {
            'PROVIDER': 'vertexai',
            'ANTHROPIC_API_KEY': 'config_api_key',
        }
        
        # Setup API credentials
        with patch('q_cli.io.config.validate_config'):
            provider, api_key = setup_api_credentials(args, config_vars, mock_console, None)
        
        # Verify args take precedence
        assert provider == 'anthropic'
        assert api_key == 'arg_api_key'

    def test_setup_api_credentials_vertexai_missing_project_id(self, mock_console, temp_env):
        """Test VertexAI provider missing project ID."""
        # Create mock args
        args = MagicMock()
        args.provider = 'vertexai'
        args.api_key = None
        
        # Create config vars with missing project ID
        config_vars = {
            'PROVIDER': 'vertexai',
            'VERTEXAI_API_KEY': 'test_api_key',
            'VERTEXAI_LOCATION': 'us-central1',
        }
        
        # Setup API credentials
        with patch('q_cli.io.config.validate_config'):
            with pytest.raises(SystemExit):
                setup_api_credentials(args, config_vars, mock_console, None)
            
            # Verify error message was printed
            assert mock_console.print.call_count >= 1
            assert 'ERROR' in mock_console.print.call_args_list[0][0][0]
            assert 'project ID' in mock_console.print.call_args_list[0][0][0]

    def test_setup_api_credentials_vertexai_missing_location(self, mock_console, temp_env):
        """Test VertexAI provider missing location."""
        # Create mock args
        args = MagicMock()
        args.provider = 'vertexai'
        args.api_key = None
        
        # Create config vars with missing location
        config_vars = {
            'PROVIDER': 'vertexai',
            'VERTEXAI_API_KEY': 'test_api_key',
            'VERTEXAI_PROJECT': 'test-project',
        }
        
        # Setup API credentials
        with patch('q_cli.io.config.validate_config'):
            with pytest.raises(SystemExit):
                setup_api_credentials(args, config_vars, mock_console, None)
            
            # Verify error message was printed
            assert mock_console.print.call_count >= 1
            assert 'ERROR' in mock_console.print.call_args_list[0][0][0]
            assert 'location' in mock_console.print.call_args_list[0][0][0]

    def test_setup_api_credentials_vertexai_with_comments(self, mock_console, temp_env):
        """Test setup_api_credentials with VertexAI and commented values."""
        # Create mock args
        args = MagicMock()
        args.provider = None
        args.api_key = None
        
        # Create config vars with commented values
        config_vars = {
            'PROVIDER': 'vertexai',
            'VERTEXAI_API_KEY': '/path/to/service-account.json  # Path to service account file',
            'VERTEXAI_PROJECT': 'test-project  # Project ID',
            'VERTEXAI_LOCATION': 'us-central1  # Location',
        }
        
        # Setup API credentials
        with patch('q_cli.io.config.validate_config'):
            with patch('q_cli.cli.llm_setup.get_debug', return_value=False):
                provider, api_key = setup_api_credentials(args, config_vars, mock_console, None)
            
            # Verify comments were stripped
            assert provider == 'vertexai'
            assert api_key == '/path/to/service-account.json'
            
            # Verify provider kwargs are set correctly
            assert hasattr(args, 'provider_kwargs')
            assert args.provider_kwargs['project_id'] == 'test-project'
            assert args.provider_kwargs['location'] == 'us-central1'

    def test_setup_api_credentials_groq_with_comments(self, mock_console, temp_env):
        """Test setup_api_credentials with Groq and commented values."""
        # Create mock args
        args = MagicMock()
        args.provider = None
        args.api_key = None
        
        # Create config vars with commented values
        config_vars = {
            'PROVIDER': 'groq',
            'GROQ_API_KEY': 'gsk_123456  # API key',
            'GROQ_MAX_TOKENS': '32000  # Default token limit',
        }
        
        # Setup API credentials
        with patch('q_cli.io.config.validate_config'):
            provider, api_key = setup_api_credentials(args, config_vars, mock_console, None)
        
        # Verify comments were stripped
        assert provider == 'groq'
        assert api_key == 'gsk_123456'

    def test_setup_api_credentials_openai_with_comments(self, mock_console, temp_env):
        """Test setup_api_credentials with OpenAI and commented values."""
        # Create mock args
        args = MagicMock()
        args.provider = None
        args.api_key = None
        
        # Create config vars with commented values
        config_vars = {
            'PROVIDER': 'openai',
            'OPENAI_API_KEY': 'sk_123456  # API key',
            'OPENAI_MAX_TOKENS': '8192  # Default token limit',
        }
        
        # Setup API credentials
        with patch('q_cli.io.config.validate_config'):
            provider, api_key = setup_api_credentials(args, config_vars, mock_console, None)
        
        # Verify comments were stripped
        assert provider == 'openai'
        assert api_key == 'sk_123456'

    def test_setup_api_credentials_unsupported_provider(self, mock_console, temp_env):
        """Test setup_api_credentials with unsupported provider."""
        # Create mock args
        args = MagicMock()
        args.provider = 'unsupported'
        args.api_key = 'test_api_key'
        
        # Create config vars
        config_vars = {}
        
        # Setup API credentials
        with patch('q_cli.io.config.validate_config'):
            with pytest.raises(SystemExit):
                setup_api_credentials(args, config_vars, mock_console, None)
            
            # Verify error message was printed
            assert mock_console.print.call_count >= 1
            assert 'Error' in mock_console.print.call_args_list[0][0][0]
            assert 'not supported' in mock_console.print.call_args_list[0][0][0]

    def test_setup_api_credentials_config_validation_error(self, mock_console, temp_env):
        """Test setup_api_credentials with config validation error."""
        # Create mock args
        args = MagicMock()
        args.provider = None
        args.api_key = None
        
        # Create config vars
        config_vars = {}
        
        # Setup API credentials
        with patch('q_cli.io.config.validate_config', side_effect=ValueError('Config error')):
            with pytest.raises(SystemExit):
                setup_api_credentials(args, config_vars, mock_console, None)
            
            # Verify error message was printed
            assert mock_console.print.call_count >= 1
            assert 'Error' in mock_console.print.call_args_list[0][0][0]
            assert 'Config error' in mock_console.print.call_args_list[0][0][0]

    def test_setup_api_credentials_config_validation_error_with_provider_override(self, mock_console, temp_env):
        """Test config validation error but provider override via args."""
        # Create mock args
        args = MagicMock()
        args.provider = 'anthropic'
        args.api_key = 'test_api_key'
        
        # Create config vars
        config_vars = {}
        
        # Setup API credentials
        with patch('q_cli.io.config.validate_config', side_effect=ValueError('Config error')):
            provider, api_key = setup_api_credentials(args, config_vars, mock_console, None)
            
            # Verify warning was printed but execution continued
            assert mock_console.print.call_count >= 1
            assert 'Warning' in mock_console.print.call_args_list[0][0][0]
            assert 'Config validation failed' in mock_console.print.call_args_list[0][0][0]
            
            # Verify provider and API key were set correctly
            assert provider == 'anthropic'
            assert api_key == 'test_api_key'

    def test_setup_api_credentials_env_var_fallback(self, mock_console, temp_env):
        """Test fallback to environment variables for API key."""
        # Create mock args
        args = MagicMock()
        args.provider = 'anthropic'
        args.api_key = None
        
        # Set environment variable
        os.environ['ANTHROPIC_API_KEY'] = 'env_api_key'
        
        # Create empty config vars
        config_vars = {}
        
        # Setup API credentials
        with patch('q_cli.io.config.validate_config'):
            provider, api_key = setup_api_credentials(args, config_vars, mock_console, None)
            
            # Verify environment variable was used
            assert provider == 'anthropic'
            assert api_key == 'env_api_key'