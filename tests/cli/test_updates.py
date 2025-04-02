"""Tests for update functionality."""

import sys
import subprocess
import pytest
from unittest.mock import patch, MagicMock

from q_cli.cli.updates import (
    handle_update_command,
    update_command,
    check_updates_async
)


class TestUpdates:
    """Tests for update functionality."""
    
    def test_handle_update_command_with_flag(self):
        """Test handling update command with update flag set."""
        # Create mock args
        args = MagicMock()
        args.update = True
        
        # Patch update_command to avoid actual execution
        with patch('q_cli.cli.updates.update_command') as mock_update:
            result = handle_update_command(args)
            
            # Verify result and that update_command was called
            assert result is True
            mock_update.assert_called_once()
    
    def test_handle_update_command_without_flag(self):
        """Test handling update command without update flag."""
        # Create mock args
        args = MagicMock()
        args.update = False
        
        # Patch update_command to ensure it's not called
        with patch('q_cli.cli.updates.update_command') as mock_update:
            result = handle_update_command(args)
            
            # Verify result and that update_command was not called
            assert result is False
            mock_update.assert_not_called()
    
    @patch('subprocess.check_call')
    @patch('sys.exit')
    def test_update_command_success(self, mock_exit, mock_check_call):
        """Test update command with successful subprocess call."""
        # Call function
        update_command()
        
        # Verify subprocess.check_call was called with the right command
        mock_check_call.assert_called_once()
        call_args = mock_check_call.call_args[0][0]
        assert call_args[0] == sys.executable
        assert call_args[1:5] == ['-m', 'pip', 'install', '--upgrade']
        assert 'github.com' in call_args[5]
        
        # Verify sys.exit was called
        mock_exit.assert_called_once_with(0)
    
    @patch('subprocess.check_call')
    @patch('sys.exit')
    def test_update_command_failure(self, mock_exit, mock_check_call):
        """Test update command with failed subprocess call."""
        # Set up check_call to raise an exception
        mock_check_call.side_effect = subprocess.CalledProcessError(1, 'pip')
        
        # Call function
        update_command()
        
        # Verify subprocess.check_call was called
        mock_check_call.assert_called_once()
        
        # Verify sys.exit was called even after error
        mock_exit.assert_called_once_with(0)
    
    @patch('q_cli.cli.updates.Thread')
    def test_check_updates_async(self, mock_thread):
        """Test asynchronous update checking."""
        # Create mock console
        console = MagicMock()
        
        # Setup mock thread
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance
        
        # Call function
        check_updates_async(console)
        
        # Verify thread was created and started
        mock_thread.assert_called_once()
        mock_thread_instance.start.assert_called_once()
        assert mock_thread_instance.daemon is True
    
    @patch('q_cli.cli.updates.check_for_updates')
    @patch('q_cli.cli.updates.is_newer_version')
    @patch('q_cli.cli.updates.get_debug', return_value=True)
    @patch('q_cli.cli.updates.Thread')
    def test_async_check_update_with_new_version(self, mock_thread, mock_debug, mock_is_newer, mock_check):
        """Test _check_update thread function when new version is available."""
        # Create mock console
        console = MagicMock()
        
        # Setup mocks
        mock_check.return_value = (True, '1.0.0')
        mock_is_newer.return_value = True
        
        # Call the thread target function directly
        with patch('q_cli.cli.updates.__version__', '0.9.0'):
            # Get the thread target function by simulating check_updates_async
            check_updates_async(console)
            thread_target = mock_thread.call_args[1]['target']
            
            # Call the target function
            thread_target()
            
            # Verify console messages
            console.print.assert_any_call("[dim]New version 1.0.0 available. Run 'q --update' to update.[/dim]")
            assert any('Current version: 0.9.0' in str(call) for call in console.print.call_args_list)
            assert any('Is GitHub version newer: True' in str(call) for call in console.print.call_args_list)
    
    @patch('q_cli.cli.updates.check_for_updates')
    @patch('q_cli.cli.updates.get_debug', return_value=False)
    @patch('q_cli.cli.updates.Thread')
    def test_async_check_update_no_debug(self, mock_thread, mock_debug, mock_check):
        """Test _check_update thread function with debug disabled."""
        # Create mock console
        console = MagicMock()
        
        # Setup mocks
        mock_check.return_value = (True, '1.0.0')
        
        # Call the thread target function directly
        check_updates_async(console)
        thread_target = mock_thread.call_args[1]['target']
        
        # Call the target function
        thread_target()
        
        # Verify console messages
        console.print.assert_called_once_with("[dim]New version 1.0.0 available. Run 'q --update' to update.[/dim]")
    
    @patch('q_cli.cli.updates.check_for_updates')
    @patch('q_cli.cli.updates.Thread')
    def test_async_check_update_no_new_version(self, mock_thread, mock_check):
        """Test _check_update thread function when no new version is available."""
        # Create mock console
        console = MagicMock()
        
        # Setup mocks
        mock_check.return_value = (False, '1.0.0')
        
        # Call the thread target function directly
        check_updates_async(console)
        thread_target = mock_thread.call_args[1]['target']
        
        # Call the target function
        thread_target()
        
        # Verify console was not asked to print update message
        assert not any("New version" in str(call) for call in console.print.call_args_list)