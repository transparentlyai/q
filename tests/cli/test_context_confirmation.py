"""Tests for context confirmation functionality."""

import pytest
from unittest.mock import MagicMock, patch, call

from q_cli.cli.context_setup import handle_context_confirmation


class TestContextConfirmation:
    """Tests for context confirmation functionality."""
    
    def test_handle_context_confirmation_flag_not_set(self):
        """Test handle_context_confirmation when confirm_context flag is not set."""
        # Create mock args
        args = MagicMock()
        args.confirm_context = False
        
        # Create mock prompt session and console
        prompt_session = MagicMock()
        console = MagicMock()
        
        # Call function
        result = handle_context_confirmation(
            args, prompt_session, "Test context", "Test system prompt", console
        )
        
        # Verify result and that confirm_context was not called
        assert result is True
        console.print.assert_not_called()
    
    @patch("q_cli.cli.context_setup.confirm_context")
    def test_handle_context_confirmation_flag_set_and_accepted(self, mock_confirm_context):
        """Test handle_context_confirmation when confirm_context flag is set and user accepts."""
        # Create mock args
        args = MagicMock()
        args.confirm_context = True
        
        # Create mock prompt session and console
        prompt_session = MagicMock()
        console = MagicMock()
        
        # Setup mock confirm_context to return True
        mock_confirm_context.return_value = True
        
        # Call function
        result = handle_context_confirmation(
            args, prompt_session, "Test context", "Test system prompt", console
        )
        
        # Verify result
        assert result is True
        
        # Verify confirm_context was called
        mock_confirm_context.assert_called_once_with(
            prompt_session, "Test system prompt", console
        )
        
        # Verify sanitized context was displayed
        console.print.assert_any_call("\n[bold cyan]Sanitized Context:[/bold cyan]")
        console.print.assert_any_call("Test context")
    
    @patch("q_cli.cli.context_setup.confirm_context")
    def test_handle_context_confirmation_flag_set_and_rejected(self, mock_confirm_context):
        """Test handle_context_confirmation when confirm_context flag is set and user rejects."""
        # Create mock args
        args = MagicMock()
        args.confirm_context = True
        
        # Create mock prompt session and console
        prompt_session = MagicMock()
        console = MagicMock()
        
        # Setup mock confirm_context to return False
        mock_confirm_context.return_value = False
        
        # Call function
        result = handle_context_confirmation(
            args, prompt_session, "Test context", "Test system prompt", console
        )
        
        # Verify result
        assert result is False
        
        # Verify confirm_context was called
        mock_confirm_context.assert_called_once_with(
            prompt_session, "Test system prompt", console
        )
        
        # Verify rejection message was displayed
        console.print.assert_any_call("Context rejected. Exiting.", style="info")
    
    @patch("q_cli.cli.context_setup.confirm_context")
    def test_handle_context_confirmation_with_empty_context(self, mock_confirm_context):
        """Test handle_context_confirmation with empty sanitized context."""
        # Create mock args
        args = MagicMock()
        args.confirm_context = True
        
        # Create mock prompt session and console
        prompt_session = MagicMock()
        console = MagicMock()
        
        # Setup mock confirm_context to return True
        mock_confirm_context.return_value = True
        
        # Call function with empty context
        result = handle_context_confirmation(
            args, prompt_session, "", "Test system prompt", console
        )
        
        # Verify result
        assert result is True
        
        # Verify confirm_context was called
        mock_confirm_context.assert_called_once_with(
            prompt_session, "Test system prompt", console
        )
        
        # Verify no sanitized context section was displayed
        assert not any(
            call == call("\n[bold cyan]Sanitized Context:[/bold cyan]") 
            for call in console.print.call_args_list
        )