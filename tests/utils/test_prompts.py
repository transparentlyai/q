"""Tests for the prompts utility module."""

import os
import pytest
from unittest.mock import patch, mock_open

from q_cli.utils.prompts import (
    load_prompt,
    get_prompt,
    get_system_prompt,
    get_command_result_prompt
)


class TestPrompts:
    """Tests for prompt loading and variable substitution."""

    @patch("builtins.open", new_callable=mock_open, read_data="Test prompt content")
    @patch("os.path.join")
    def test_load_prompt(self, mock_join, mock_file):
        """Test loading a prompt from file."""
        # Setup
        mock_join.return_value = "/path/to/prompt.md"
        
        # Execute
        result = load_prompt("prompt")
        
        # Verify
        mock_join.assert_called_once()
        mock_file.assert_called_once_with("/path/to/prompt.md", "r")
        assert result == "Test prompt content"

    @patch("builtins.open", new_callable=mock_open, read_data="Hello {name}!")
    def test_get_prompt_simple_variable(self, mock_file):
        """Test substituting a simple variable in a prompt."""
        # Execute
        result = get_prompt("/path/to/prompt.md", name="World")
        
        # Verify
        mock_file.assert_called_once_with("/path/to/prompt.md", "r")
        assert result == "Hello World!"

    @patch("builtins.open", new_callable=mock_open, read_data="Your are currently using test_model as your primary model")
    @patch("re.sub")
    def test_get_prompt_model_substitution(self, mock_sub, mock_file):
        """Test model name substitution in a prompt."""
        # Setup
        mock_sub.return_value = "Your are currently using claude-3 as your primary model"
        
        # Execute
        result = get_prompt("/path/to/prompt.md", model="claude-3")
        
        # Verify
        mock_file.assert_called_once_with("/path/to/prompt.md", "r")
        assert "claude-3" in mock_sub.call_args[0][1]
        assert result == "Your are currently using claude-3 as your primary model"

    @patch("builtins.open", new_callable=mock_open, read_data="User context:\n{usercontext}\n\nProject context:\n{projectcontext}")
    def test_variable_names_exact_match(self, mock_file):
        """Test that variable names in templates must match exactly (usercontext not usercontex)."""
        # Execute
        result = get_prompt("/path/to/prompt.md", 
                           usercontext="User specific instructions", 
                           projectcontext="Project guidelines")
        
        # Verify correct substitution
        assert "User context:\nUser specific instructions" in result
        assert "Project context:\nProject guidelines" in result
        
        # This should not raise a KeyError with exact matching variable names

    @patch("builtins.open", new_callable=mock_open, read_data="User context:\n{usercontext}\n\nProject context:\n{projectcontext}")
    def test_missing_variable_with_typo(self, mock_file):
        """Test that variables with typos in their names are not used for substitution."""
        # Test with misspelled variable name
        result = get_prompt("/path/to/prompt.md", 
                          usercontex="This has a typo in the parameter name", 
                          projectcontext="Project guidelines")
        
        # Verify empty string was used for usercontext (not the typo variable)
        assert "User context:\n\n" in result
        assert "Project context:\nProject guidelines" in result

    @patch("os.path.join")
    @patch("q_cli.utils.prompts.get_prompt")
    @patch("q_cli.utils.helpers.get_working_and_project_dirs")
    def test_get_system_prompt_with_context_vars(self, mock_get_dirs, mock_get_prompt, mock_join):
        """Test get_system_prompt with context variables."""
        # Setup
        mock_join.return_value = "/path/to/base_system_prompt.md"
        mock_get_prompt.return_value = "System prompt with substituted variables"
        mock_get_dirs.return_value = "Current Working Directory: /test/dir\nProject Root Directory: /test/project"
        
        # Execute
        result = get_system_prompt(
            model="claude-3",
            usercontext="User context data",
            projectcontext="Project context data"
        )
        
        # Verify
        mock_join.assert_called_once()
        mock_get_dirs.assert_called_once()
        mock_get_prompt.assert_called_once_with(
            "/path/to/base_system_prompt.md", 
            model="claude-3", 
            usercontext="User context data", 
            projectcontext="Project context data",
            directories="Current Working Directory: /test/dir\nProject Root Directory: /test/project"
        )
        assert result == "System prompt with substituted variables"

    @patch("os.path.join")
    @patch("q_cli.utils.prompts.get_prompt")
    @patch("q_cli.utils.helpers.get_working_and_project_dirs")
    def test_get_system_prompt_with_legacy_context(self, mock_get_dirs, mock_get_prompt, mock_join):
        """Test get_system_prompt with legacy context parameter."""
        # Setup
        mock_join.side_effect = [
            "/path/to/base_system_prompt.md",
            "/path/to/context_prompt.md"
        ]
        mock_get_prompt.side_effect = [
            "Base system prompt", 
            "Context: Legacy context data"
        ]
        mock_get_dirs.return_value = "Current Working Directory: /test/dir\nProject Root Directory: /test/project"
        
        # Execute
        result = get_system_prompt(context="Legacy context data")
        
        # Verify
        assert mock_join.call_count == 2
        assert mock_get_prompt.call_count == 2
        mock_get_dirs.assert_called_once()
        # First call should be for base system prompt
        assert mock_get_prompt.call_args_list[0][0][0] == "/path/to/base_system_prompt.md"
        # Verify directories variable is passed to the first call
        assert mock_get_prompt.call_args_list[0][1]["directories"] == "Current Working Directory: /test/dir\nProject Root Directory: /test/project"
        # Second call should be for context prompt
        assert mock_get_prompt.call_args_list[1][0][0] == "/path/to/context_prompt.md"
        assert "Legacy context data" in mock_get_prompt.call_args_list[1][1]["context"]
        assert result == "Base system prompt\n\nContext: Legacy context data"

    @patch("os.path.join")
    @patch("q_cli.utils.prompts.get_prompt")
    def test_get_command_result_prompt(self, mock_get_prompt, mock_join):
        """Test get_command_result_prompt."""
        # Setup
        mock_join.return_value = "/path/to/command_result_prompt.md"
        mock_get_prompt.return_value = "Command results: test output"
        
        # Execute
        result = get_command_result_prompt("test output")
        
        # Verify
        mock_join.assert_called_once()
        mock_get_prompt.assert_called_once_with(
            "/path/to/command_result_prompt.md", 
            results="test output"
        )
        assert result == "Command results: test output"

    @patch("os.path.join")
    @patch("q_cli.utils.prompts.get_prompt")
    def test_get_command_result_prompt_fallback(self, mock_get_prompt, mock_join):
        """Test get_command_result_prompt fallback when file not found."""
        # Setup
        mock_join.return_value = "/path/to/command_result_prompt.md"
        mock_get_prompt.side_effect = FileNotFoundError("File not found")
        
        # Execute
        result = get_command_result_prompt("test output")
        
        # Verify
        mock_join.assert_called_once()
        mock_get_prompt.assert_called_once()
        assert "Result from last command:" in result
        assert "test output" in result

    @patch("builtins.open", new_callable=mock_open, read_data="Context: {context}")
    def test_backwards_compatibility(self, mock_file):
        """Test that the old context parameter still works."""
        # Execute 
        result = get_prompt("/path/to/prompt.md", context="Legacy context")
        
        # Verify
        assert result == "Context: Legacy context"

    # Integration-style tests combining components
    @patch("builtins.open")
    @patch("os.path.join")
    def test_integration_usercontext_and_projectcontext(self, mock_join, mock_open):
        """Integration test for usercontext and projectcontext substitution."""
        # Setup mock files
        base_prompt_content = "User context:\n{usercontext}\n\nProject context:\n{projectcontext}"
        mock_file_handle = mock_open.return_value.__enter__.return_value
        mock_file_handle.read.return_value = base_prompt_content
        
        mock_join.return_value = "/path/to/base_system_prompt.md"
        
        # Execute
        result = get_system_prompt(
            usercontext="User specific instructions", 
            projectcontext="Project guidelines",
            model="claude-3"
        )
        
        # Verify
        assert "User context:\nUser specific instructions" in result
        assert "Project context:\nProject guidelines" in result
        
    @patch("builtins.open")
    @patch("os.path.join")
    def test_empty_context_variables(self, mock_join, mock_open):
        """Test that the prompt works correctly with no context variables provided."""
        # Setup mock files
        base_prompt_content = "User context:\n{usercontext}\n\nProject context:\n{projectcontext}"
        mock_file_handle = mock_open.return_value.__enter__.return_value
        mock_file_handle.read.return_value = base_prompt_content
        
        mock_join.return_value = "/path/to/base_system_prompt.md"
        
        # Execute - test without providing usercontext or projectcontext
        result = get_system_prompt(model="claude-3")
        
        # Verify the empty substitutions work (no KeyError)
        assert "User context:\n" in result
        assert "Project context:\n" in result