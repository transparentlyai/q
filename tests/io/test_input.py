"""Tests for input module."""

import pytest
from unittest.mock import patch, MagicMock, call

from q_cli.io.input import confirm_context


class TestInput:
    """Tests for input functions."""
    
    @patch("q_cli.io.input.get_input")
    def test_confirm_context_accepted(self, mock_get_input):
        """Test context confirmation with user accepting."""
        # Setup
        prompt_session = MagicMock()
        console = MagicMock()
        system_prompt = "test system prompt"
        
        # Mock user input accepting (Y or y)
        mock_get_input.return_value = "y"
        
        # Call function
        result = confirm_context(prompt_session, system_prompt, console)
        
        # Verify
        assert result is True
        # Check correct console prints were called
        assert console.print.call_args_list[0] == call("\n[bold magenta]System prompt that will be sent to Q:[/bold magenta]")
        mock_get_input.assert_called_once_with("Proceed with this system prompt? [Y/n] ", session=prompt_session)

    @patch("q_cli.io.input.get_input")
    def test_confirm_context_rejected(self, mock_get_input):
        """Test context confirmation with user rejecting."""
        # Setup
        prompt_session = MagicMock()
        console = MagicMock()
        system_prompt = "test system prompt"
        
        # Mock user input rejecting (N or n)
        mock_get_input.return_value = "n"
        
        # Call function
        result = confirm_context(prompt_session, system_prompt, console)
        
        # Verify
        assert result is False
        mock_get_input.assert_called_once_with("Proceed with this system prompt? [Y/n] ", session=prompt_session)

    @patch("q_cli.io.input.get_input")
    def test_confirm_context_default_yes(self, mock_get_input):
        """Test context confirmation with user pressing enter (default yes)."""
        # Setup
        prompt_session = MagicMock()
        console = MagicMock()
        system_prompt = "test system prompt"
        
        # Mock user input with empty string (default yes)
        mock_get_input.return_value = ""
        
        # Call function
        result = confirm_context(prompt_session, system_prompt, console)
        
        # Verify
        assert result is True
        mock_get_input.assert_called_once_with("Proceed with this system prompt? [Y/n] ", session=prompt_session)

    @patch("q_cli.io.input.get_input")
    def test_confirm_context_invalid_then_yes(self, mock_get_input):
        """Test context confirmation with initial invalid input then yes."""
        # Setup
        prompt_session = MagicMock()
        console = MagicMock()
        system_prompt = "test system prompt"
        
        # Mock user input with invalid input first, then yes
        mock_get_input.side_effect = ["invalid", "y"]
        
        # Call function
        result = confirm_context(prompt_session, system_prompt, console)
        
        # Verify
        assert result is True
        assert mock_get_input.call_count == 2
        assert mock_get_input.call_args_list[0] == call("Proceed with this system prompt? [Y/n] ", session=prompt_session)
        assert mock_get_input.call_args_list[1] == call("Proceed with this system prompt? [Y/n] ", session=prompt_session)
        # Check that warning was printed
        console.print.assert_any_call("Please answer Y or N", style="warning")