"""Tests for CLI argument parsing."""

import sys
import argparse
import subprocess
import pytest
from unittest.mock import patch, MagicMock

from q_cli.cli.args import setup_argparse, update_command


class TestCLIArgs:
    """Tests for CLI argument parsing."""
    
    def test_setup_argparse(self):
        """Test that the argument parser is set up correctly with all options."""
        # Call the function
        parser = setup_argparse()
        
        # Basic assertions
        assert isinstance(parser, argparse.ArgumentParser)
        assert "Send a question to Q and get the response" in parser.description
        
        # Helper function to find action by dest
        def find_action(dest):
            for action in parser._actions:
                if action.dest == dest:
                    return action
            return None
        
        # Check all expected arguments
        positional_args = [a for a in parser._actions if a.dest == 'question']
        assert len(positional_args) == 1, "Should have 'question' positional argument"
        assert positional_args[0].nargs == '*'
        
        # File input option
        file_action = find_action('file')
        assert file_action is not None
        assert file_action.option_strings == ['--file', '-f']
        
        # API key option
        api_key_action = find_action('api_key')
        assert api_key_action is not None
        assert api_key_action.option_strings == ['--api-key', '-k']
        
        # Model option
        model_action = find_action('model')
        assert model_action is not None
        assert model_action.option_strings == ['--model', '-m']
        
        # Provider option
        provider_action = find_action('provider')
        assert provider_action is not None
        assert provider_action.option_strings == ['--provider']
        assert provider_action.choices == ['anthropic', 'vertexai', 'groq', 'openai']
        
        # Interactive mode options
        no_interactive_action = find_action('no_interactive')
        assert no_interactive_action is not None
        assert no_interactive_action.option_strings == ['--no-interactive', '-i']
        
        interactive_action = find_action('interactive')
        assert interactive_action is not None
        assert interactive_action.option_strings == ['--interactive']
        
        # Context and formatting options
        no_context_action = find_action('no_context')
        assert no_context_action is not None
        assert no_context_action.option_strings == ['--no-context', '-c']
        
        no_md_action = find_action('no_md')
        assert no_md_action is not None
        assert no_md_action.option_strings == ['--no-md', '-p']
        
        # Additional context file option
        context_file_action = find_action('context_file')
        assert context_file_action is not None
        assert context_file_action.option_strings == ['--context-file', '-x']
        # Check that it's an append action
        from argparse import _AppendAction
        assert isinstance(context_file_action, _AppendAction)
        
        # Context confirmation option
        confirm_context_action = find_action('confirm_context')
        assert confirm_context_action is not None
        assert confirm_context_action.option_strings == ['--confirm-context', '-w']
        
        # Empty input option
        no_empty_action = find_action('no_empty')
        assert no_empty_action is not None
        assert no_empty_action.option_strings == ['--no-empty', '-e']
        
        # Security options
        no_execute_action = find_action('no_execute')
        assert no_execute_action is not None
        assert no_execute_action.option_strings == ['--no-execute']
        
        no_web_action = find_action('no_web')
        assert no_web_action is not None
        assert no_web_action.option_strings == ['--no-web']
        
        no_file_write_action = find_action('no_file_write')
        assert no_file_write_action is not None
        assert no_file_write_action.option_strings == ['--no-file-write']
        
        # Context options
        file_tree_action = find_action('file_tree')
        assert file_tree_action is not None
        assert file_tree_action.option_strings == ['--file-tree']
        
        max_context_tokens_action = find_action('max_context_tokens')
        assert max_context_tokens_action is not None
        assert max_context_tokens_action.option_strings == ['--max-context-tokens']
        assert max_context_tokens_action.type == int
        
        context_priority_mode_action = find_action('context_priority_mode')
        assert context_priority_mode_action is not None
        assert context_priority_mode_action.option_strings == ['--context-priority-mode']
        assert context_priority_mode_action.choices == ['balanced', 'code', 'conversation']
        
        # Misc options
        context_stats_action = find_action('context_stats')
        assert context_stats_action is not None
        assert context_stats_action.option_strings == ['--context-stats']
        
        version_action = find_action('version')
        assert version_action is not None
        assert version_action.option_strings == ['--version', '-v']
        
        update_action = find_action('update')
        assert update_action is not None
        assert update_action.option_strings == ['--update']
        
        recover_action = find_action('recover')
        assert recover_action is not None
        assert recover_action.option_strings == ['--recover']
        
        dry_run_action = find_action('dry_run')
        assert dry_run_action is not None
        assert dry_run_action.option_strings == ['--dry-run']
        
        yes_action = find_action('yes')
        assert yes_action is not None
        assert yes_action.option_strings == ['--yes']
        
        debug_action = find_action('debug')
        assert debug_action is not None
        assert debug_action.option_strings == ['--debug']
    
    def test_argument_parsing_question(self):
        """Test parsing a question from arguments."""
        # Set up the parser
        parser = setup_argparse()
        
        # Parse arguments
        args = parser.parse_args(['What', 'is', 'the', 'answer?'])
        
        # Check the result
        assert args.question == ['What', 'is', 'the', 'answer?']
        assert not args.no_interactive
        
    def test_argument_parsing_flags(self):
        """Test parsing various flag arguments."""
        # Set up the parser
        parser = setup_argparse()
        
        # Parse arguments with various flags
        args = parser.parse_args(['--no-interactive', '--no-md', '--no-context', '--file-tree', '--debug', 'test'])
        
        # Check the result
        assert args.question == ['test']
        assert args.no_interactive
        assert args.no_md
        assert args.no_context
        assert args.file_tree
        assert args.debug
        
    def test_argument_parsing_value_options(self):
        """Test parsing arguments with values."""
        # Set up the parser
        parser = setup_argparse()
        
        # Parse arguments with options that take values
        args = parser.parse_args([
            '--model', 'claude-3-5-sonnet',
            '--provider', 'anthropic',
            '--api-key', 'test-key',
            '--file', 'question.txt',
            '--max-context-tokens', '100000',
            '--context-priority-mode', 'code',
        ])
        
        # Check the result
        assert args.model == 'claude-3-5-sonnet'
        assert args.provider == 'anthropic'
        assert args.api_key == 'test-key'
        assert args.file == 'question.txt'
        assert args.max_context_tokens == 100000
        assert args.context_priority_mode == 'code'
        
    def test_argument_parsing_interactive_force(self):
        """Test forcing interactive mode."""
        # Set up the parser
        parser = setup_argparse()
        
        # Parse arguments with interactive flag
        args = parser.parse_args(['--interactive'])
        
        # Check the result
        assert args.interactive
        assert not args.question
        
    def test_argument_parsing_context_file_multiple(self):
        """Test adding multiple context files."""
        # Set up the parser
        parser = setup_argparse()
        
        # Parse arguments with multiple context files
        args = parser.parse_args([
            '--context-file', 'file1.md',
            '--context-file', 'file2.md',
            'question'
        ])
        
        # Check the result
        assert args.context_file == ['file1.md', 'file2.md']
        assert args.question == ['question']
        
    def test_argument_parsing_security_options(self):
        """Test parsing security-related options."""
        # Set up the parser
        parser = setup_argparse()
        
        # Parse arguments with security options
        args = parser.parse_args([
            '--no-execute',
            '--no-web',
            '--no-file-write',
            'question'
        ])
        
        # Check the result
        assert args.no_execute
        assert args.no_web
        assert args.no_file_write
        assert args.question == ['question']
        
    def test_argument_parsing_short_options(self):
        """Test parsing short option forms."""
        # Set up the parser
        parser = setup_argparse()
        
        # Parse arguments with short options
        args = parser.parse_args([
            '-i',  # no-interactive
            '-c',  # no-context
            '-p',  # no-md
            '-f', 'file.txt',  # file
            '-m', 'model-name',  # model
            '-k', 'api-key',  # api-key
            '-x', 'context.md',  # context-file
            '-e',  # no-empty
            '-w',  # confirm-context
            'question'
        ])
        
        # Check the result
        assert args.no_interactive
        assert args.no_context
        assert args.no_md
        assert args.file == 'file.txt'
        assert args.model == 'model-name'
        assert args.api_key == 'api-key'
        assert args.context_file == ['context.md']
        assert args.no_empty
        assert args.confirm_context
        assert args.question == ['question']
        
    def test_argument_parsing_mutually_exclusive(self):
        """Test that mutually exclusive options can't be used together."""
        # Set up the parser
        parser = setup_argparse()
        
        # Try to parse arguments with mutually exclusive options
        with pytest.raises(SystemExit):
            parser.parse_args(['--no-interactive', '--interactive'])
            
    def test_argument_parsing_default_interactive(self):
        """Test that interactive mode is forced when no arguments are provided."""
        # Set up the parser
        parser = setup_argparse()
        
        # Create empty sys.argv (simulating no arguments)
        with patch('sys.argv', ['q.py']):
            # We need to patch __main__ to avoid actual execution
            with patch('q_cli.cli.args.setup_argparse') as mock_setup:
                # Make setup_argparse return our parser
                mock_setup.return_value = parser
                
                from q_cli.cli.main import initialize_cli
                with patch('q_cli.cli.main.setup_console'):
                    args, _ = initialize_cli()
                
                # Check that --interactive was added
                assert args.interactive
                
    @patch('subprocess.check_call')
    @patch('sys.exit')
    def test_update_command_success(self, mock_exit, mock_check_call):
        """Test the update command when it succeeds."""
        # Call the function
        update_command()
        
        # Check that subprocess.check_call was called with the right arguments
        mock_check_call.assert_called_once()
        call_args = mock_check_call.call_args[0][0]
        assert call_args[0] == sys.executable
        assert call_args[1:5] == ['-m', 'pip', 'install', '--upgrade']
        assert 'github.com' in call_args[5]
        
        # Check that sys.exit was called
        mock_exit.assert_called_once_with(0)
        
    @patch('subprocess.check_call')
    @patch('sys.exit')
    def test_update_command_failure(self, mock_exit, mock_check_call):
        """Test the update command when it fails."""
        # Set up the mock to raise an exception
        mock_check_call.side_effect = subprocess.CalledProcessError(1, 'pip')
        
        # Call the function
        update_command()
        
        # Check that subprocess.check_call was called
        mock_check_call.assert_called_once()
        
        # Check that sys.exit was called
        mock_exit.assert_called_once_with(0)