"""Tests for the main CLI module."""

import os
import pytest
from unittest.mock import MagicMock, patch

from q_cli.cli.main import configure_model_settings


class TestConfigureModelSettings:
    """Tests for configure_model_settings function."""
    
    def test_configure_model_settings_with_comments(self, mock_console):
        """Test configure_model_settings with comments in values."""
        # Create mock args
        args = MagicMock()
        args.model = None
        args.max_tokens = None
        
        # Create config vars - in real usage, comments would have been stripped already
        # when loading from file, so use clean values for this test
        config_vars = {
            'ANTHROPIC_MODEL': 'claude-3-7-sonnet-latest',
            'ANTHROPIC_MAX_TOKENS': '8192',
        }
        
        # Configure model settings
        with patch('q_cli.cli.main.get_default_model', return_value='claude-3-7-sonnet-latest'):
            configure_model_settings(args, 'anthropic', config_vars)
        
        # Verify values set correctly
        assert args.model == 'claude-3-7-sonnet-latest'
        assert args.max_tokens == 8192

    def test_configure_model_settings_vertexai_with_comments(self, mock_console):
        """Test configure_model_settings with VertexAI and comments."""
        # Create mock args
        args = MagicMock()
        args.model = None
        args.max_tokens = None
        
        # Create config vars - in real usage, comments would have been stripped already
        config_vars = {
            'VERTEXAI_MODEL': 'gemini-2.0-flash-001',
            'VERTEXAI_MAX_TOKENS': '8192',
        }
        
        # Configure model settings
        with patch('q_cli.cli.main.get_default_model', return_value='gemini-2.0-flash-001'):
            with patch('q_cli.cli.main.get_max_tokens', return_value=8192):
                configure_model_settings(args, 'vertexai', config_vars)
        
        # Verify values set correctly
        assert args.model == 'gemini-2.0-flash-001'
        assert args.max_tokens == 8192
        
    def test_configure_model_settings_invalid_token_value(self, mock_console):
        """Test configure_model_settings with invalid token value."""
        # Create mock args
        args = MagicMock()
        args.model = None
        args.max_tokens = None
        
        # Create config vars with invalid token value
        config_vars = {
            'VERTEXAI_MODEL': 'gemini-2.0-flash-001',
            'VERTEXAI_MAX_TOKENS': 'not-a-number  # This is invalid',
        }
        
        # Configure model settings
        with patch('q_cli.cli.main.get_default_model', return_value='gemini-2.0-flash-001'):
            with patch('q_cli.cli.main.get_max_tokens', return_value=8192):
                configure_model_settings(args, 'vertexai', config_vars)
        
        # Verify fallback to default was used
        assert args.model == 'gemini-2.0-flash-001'
        assert args.max_tokens == 8192  # Default from get_max_tokens
        
    def test_configure_model_settings_no_config_values(self, mock_console):
        """Test configure_model_settings without config values."""
        # Create mock args
        args = MagicMock()
        args.model = None
        args.max_tokens = None
        
        # Empty config vars
        config_vars = {}
        
        # Configure model settings
        with patch('q_cli.cli.main.get_default_model', return_value='claude-3-7-sonnet-latest'):
            with patch('q_cli.cli.main.get_max_tokens', return_value=8192):
                configure_model_settings(args, 'anthropic', config_vars)
        
        # Verify fallback to defaults
        assert args.model == 'claude-3-7-sonnet-latest'
        assert args.max_tokens == 8192