"""Tests for dry run functionality."""

import pytest
from unittest.mock import MagicMock

from q_cli.cli.dry_run import handle_dry_run


class TestDryRun:
    """Tests for dry run functionality."""
    
    def test_handle_dry_run_enabled_with_question(self, mock_console):
        """Test handling dry run with dry_run flag and a question."""
        # Create mock args
        args = MagicMock()
        args.dry_run = True
        args.model = 'claude-3-5-sonnet'
        args.max_tokens = 8192
        
        # Call function
        result = handle_dry_run(
            args,
            "What is the meaning of life?",
            "You are an AI assistant",
            mock_console
        )
        
        # Verify result and console output
        assert result is True
        assert mock_console.print.call_count == 1
        
        # Check that all expected elements are in the output
        output = mock_console.print.call_args[0][0]
        assert "DRY RUN MODE" in output
        assert "Model:" in output
        assert "claude-3-5-sonnet" in output
        assert "Max tokens:" in output
        assert "8192" in output
        assert "System prompt:" in output
        assert "You are an AI assistant" in output
        assert "User message:" in output
        assert "What is the meaning of life?" in output
    
    def test_handle_dry_run_enabled_without_question(self, mock_console):
        """Test handling dry run with dry_run flag but no question."""
        # Create mock args
        args = MagicMock()
        args.dry_run = True
        args.model = 'claude-3-5-sonnet'
        args.max_tokens = 8192
        
        # Call function
        result = handle_dry_run(
            args,
            "",
            "You are an AI assistant",
            mock_console
        )
        
        # Verify result and console output
        assert result is True
        assert mock_console.print.call_count == 1
        
        # Check that "No initial user message" is in the output
        output = mock_console.print.call_args[0][0]
        assert "No initial user message" in output
    
    def test_handle_dry_run_disabled(self, mock_console):
        """Test handling dry run when dry_run flag is not set."""
        # Create mock args
        args = MagicMock()
        args.dry_run = False
        
        # Call function
        result = handle_dry_run(
            args,
            "What is the meaning of life?",
            "You are an AI assistant",
            mock_console
        )
        
        # Verify result and that console.print was not called
        assert result is False
        mock_console.print.assert_not_called()
    
    def test_handle_dry_run_missing_attribute(self, mock_console):
        """Test handling dry run when args doesn't have dry_run attribute."""
        # Create mock args without dry_run attribute
        args = MagicMock(spec=[])
        
        # Call function
        result = handle_dry_run(
            args,
            "What is the meaning of life?",
            "You are an AI assistant",
            mock_console
        )
        
        # Verify result and that console.print was not called
        assert result is False
        mock_console.print.assert_not_called()