"""Tests for helper functions module."""

import os
import pytest
from unittest.mock import patch, MagicMock

from q_cli.utils.helpers import (
    sanitize_context,
    contains_sensitive_info,
    format_markdown,
    parse_version,
    is_newer_version,
    clean_operation_codeblocks,
    expand_env_vars,
    get_working_and_project_dirs
)


class TestHelpers:
    """Tests for the helpers module."""

    def test_contains_sensitive_info(self):
        """Test that sensitive info is detected correctly."""
        # True cases
        assert contains_sensitive_info("My API key is 123456")
        assert contains_sensitive_info("The password is password123")
        assert contains_sensitive_info("secret key: abcde")
        assert contains_sensitive_info("This contains SECRET")

        # False cases
        assert not contains_sensitive_info("Regular text without sensitive info")
        assert not contains_sensitive_info("This is a normal sentence")

    def test_sanitize_context(self):
        """Test that sanitize_context properly sanitizes sensitive information."""
        mock_console = MagicMock()
        
        # Test with sensitive info
        result = sanitize_context("My API key is 123456", mock_console)
        assert "API key" not in result
        assert "[REDACTED - Potential sensitive information]" in result
        mock_console.print.assert_called_once()
        
        # Test without sensitive info
        mock_console.reset_mock()
        context = "This is safe text"
        result = sanitize_context(context, mock_console)
        assert result == context
        mock_console.print.assert_not_called()
        
        # Test with empty context
        assert sanitize_context("", mock_console) == ""

    def test_parse_version(self):
        """Test that version strings are correctly parsed."""
        assert parse_version("1.2.3") == [1, 2, 3]
        assert parse_version("0.1.0") == [0, 1, 0]
        assert parse_version("10.20.30.40") == [10, 20, 30, 40]
        
        # Test with invalid version
        assert parse_version("invalid") == [0, 0, 0]

    def test_is_newer_version(self):
        """Test version comparison logic."""
        # Basic comparisons
        assert is_newer_version("1.2.3", "1.2.2")
        assert is_newer_version("2.0.0", "1.9.9")
        assert is_newer_version("1.10.0", "1.9.0")
        
        # Equal versions
        assert not is_newer_version("1.2.3", "1.2.3")
        
        # Older versions
        assert not is_newer_version("1.2.2", "1.2.3")
        
        # Different length versions
        assert is_newer_version("1.2.3.1", "1.2.3")
        assert not is_newer_version("1.2.3", "1.2.3.1")
        
        # Edge cases
        assert is_newer_version("1.2.3", "")
        assert not is_newer_version("", "1.2.3")
        assert not is_newer_version("", "")

    def test_expand_env_vars(self):
        """Test environment variable expansion."""
        # Set a test environment variable
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            assert expand_env_vars("Value is $TEST_VAR") == "Value is test_value"
            assert expand_env_vars("Value is ${TEST_VAR}") == "Value is test_value"
            
            # Test with non-existent variable
            assert expand_env_vars("Value is $NONEXISTENT") == "Value is "
            
            # Test with no variables
            assert expand_env_vars("Plain text") == "Plain text"

    def test_clean_operation_codeblocks(self):
        """Test cleaning of code blocks around operations."""
        # Test with code block wrapping
        text = "```\noperation content\n```"
        assert clean_operation_codeblocks(text) == "operation content"
        
        # Test with language tag
        text = "```python\nprint('operation content')\n```"
        assert clean_operation_codeblocks(text) == "print('operation content')"
        
        # Test with no code block
        text = "operation content"
        assert clean_operation_codeblocks(text) == "operation content"
        
        # Test with embedded code block (shouldn't change)
        text = "explanation\n```\nembedded code\n```\nmore text"
        assert clean_operation_codeblocks(text) == text
        
        # Test with extra whitespace
        text = "  ```\noperation content\n```  "
        assert clean_operation_codeblocks(text) == "operation content"

    @patch('os.getcwd')
    @patch('os.path.isdir')
    @patch('os.path.expanduser')
    @patch('os.path.dirname')
    def test_get_working_and_project_dirs(self, mock_dirname, mock_expanduser, mock_isdir, mock_getcwd):
        """Test finding working directory and project directory."""
        # Set up mocks
        mock_getcwd.return_value = '/home/user/projects/myproject/subdir'
        mock_expanduser.return_value = '/home/user'
        
        # Mock dirname to return appropriate parent directories
        def dirname_side_effect(path):
            if path == '/home/user/projects/myproject/subdir':
                return '/home/user/projects/myproject'
            elif path == '/home/user/projects/myproject':
                return '/home/user/projects'
            elif path == '/home/user/projects':
                return '/home/user'
            elif path == '/home/user':
                return '/home'
            elif path == '/home':
                return '/'
            else:
                return os.path.dirname(path)
        
        mock_dirname.side_effect = dirname_side_effect
        
        # Case 1: .git found in current directory
        def isdir_side_effect(path):
            if path == '/home/user/projects/myproject/subdir/.git':
                return True
            return False
            
        mock_isdir.side_effect = isdir_side_effect
        
        result = get_working_and_project_dirs()
        assert "Current Working Directory: /home/user/projects/myproject/subdir" in result
        assert "Project Root Directory: /home/user/projects/myproject/subdir" in result
        
        # Case 2: .Q found in parent directory
        def isdir_side_effect2(path):
            if path == '/home/user/projects/myproject/subdir/.git' or path == '/home/user/projects/myproject/subdir/.Q':
                return False
            if path == '/home/user/projects/myproject/.git':
                return False
            if path == '/home/user/projects/myproject/.Q':
                return True
            return False
            
        mock_isdir.side_effect = isdir_side_effect2
        
        result = get_working_and_project_dirs()
        assert "Current Working Directory: /home/user/projects/myproject/subdir" in result
        assert "Project Root Directory: /home/user/projects/myproject" in result
        
        # Case 3: No project directory found
        def isdir_side_effect3(path):
            # Make sure we always return false for any .git or .Q check
            if '.git' in path or '.Q' in path:
                return False
            # Otherwise default to True to keep paths valid
            return True
            
        mock_isdir.side_effect = isdir_side_effect3
        
        result = get_working_and_project_dirs()
        assert "Current Working Directory: /home/user/projects/myproject/subdir" in result
        assert "Project Root Directory: Unknown" in result