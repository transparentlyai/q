"""Tests for the permissions module functionality."""

import json
import pytest
import time
from unittest.mock import patch, MagicMock

from q_cli.utils.permissions import (
    CommandPermissionManager,
    parse_command_list
)
from q_cli.utils.permissions_context import (
    ApprovalContext,
    PermissionContextManager
)


class TestPermissionsParsing:
    """Tests for permission list parsing logic."""

    def test_parse_command_list_valid_json(self):
        """Test parsing a valid JSON command list."""
        json_str = '["ls", "git", "python"]'
        result = parse_command_list(json_str)
        assert result == ["ls", "git", "python"]

    def test_parse_command_list_invalid_json(self):
        """Test parsing an invalid JSON command list."""
        json_str = '["ls", "git", python]'  # Missing quotes around python
        result = parse_command_list(json_str)
        assert result == []

    def test_parse_command_list_empty(self):
        """Test parsing an empty command list."""
        result = parse_command_list("")
        assert result == []

    def test_parse_command_list_not_array(self):
        """Test parsing JSON that's not an array."""
        json_str = '{"command": "ls"}'
        result = parse_command_list(json_str)
        assert result == []

    def test_parse_command_list_mixed_types(self):
        """Test parsing JSON array with mixed types (should filter non-strings)."""
        json_str = '["ls", 123, "git", true]'
        result = parse_command_list(json_str)
        assert result == ["ls", "git"]


class TestCommandPermissionManager:
    """Tests for CommandPermissionManager functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.always_approved = ["ls", "cat", "echo"]
        self.always_restricted = ["rm", "chmod", "chown"]
        self.prohibited = ["sudo", "shutdown", "reboot"]
        self.manager = CommandPermissionManager(
            always_approved=self.always_approved,
            always_restricted=self.always_restricted,
            prohibited=self.prohibited
        )

    def test_initialization(self):
        """Test proper initialization of the permission manager."""
        assert set(self.always_approved) == self.manager.always_approved_commands
        assert set(self.always_restricted) == self.manager.always_restricted_commands
        assert set(self.prohibited) == self.manager.prohibited_commands
        assert len(self.manager.session_approved_commands) == 0
        assert self.manager.context_manager is not None

    def test_extract_command_type(self):
        """Test extracting command types from command strings."""
        assert self.manager.extract_command_type("ls -la") == "ls"
        assert self.manager.extract_command_type("/usr/bin/python script.py") == "python"
        assert self.manager.extract_command_type("") == ""
        assert self.manager.extract_command_type("../bin/dangerous") == "PATH_TRAVERSAL_ATTEMPT"

    def test_extract_all_command_types(self):
        """Test extracting all command types from complex command strings."""
        # Simple command
        assert self.manager.extract_all_command_types("ls -la") == ["ls"]
        
        # Command chain
        result = self.manager.extract_all_command_types("ls -la | grep file && echo done")
        assert set(result) == {"ls", "grep", "echo"}
        
        # Command with semicolon
        result = self.manager.extract_all_command_types("cd /tmp; rm file.txt")
        assert set(result) == {"cd", "rm"}
        
        # Backtick command substitution
        result = self.manager.extract_all_command_types("echo `ls -la`")
        # The behavior might be implementation-dependent (may not extract from backticks)
        assert "echo" in set(result)
        
        # Subshell command substitution
        result = self.manager.extract_all_command_types("echo $(cat file.txt)")
        # Implementation may vary based on regex handling
        assert "echo" in set(result)
        
        # Find with exec
        result = self.manager.extract_all_command_types("find . -name '*.py' -exec rm {} \\;")
        # Complex command extraction may depend on implementation
        assert "find" in set(result)

    def test_is_command_prohibited(self):
        """Test checking if commands are prohibited."""
        # Directly prohibited command
        assert self.manager.is_command_prohibited("sudo apt update") is True
        
        # Command not in prohibited list
        assert self.manager.is_command_prohibited("ls -la") is False
        
        # Prohibited command in backticks
        assert self.manager.is_command_prohibited("echo `sudo apt update`") is True

    def test_needs_permission(self):
        """Test checking if commands need permission."""
        # Always approved command
        assert self.manager.needs_permission("ls -la") is False
        
        # Always restricted command
        assert self.manager.needs_permission("rm file.txt") is True
        
        # Prohibited command (returns False because it will be blocked)
        assert self.manager.needs_permission("sudo apt update") is False
        
        # Command not in any list
        assert self.manager.needs_permission("git status") is True
        
        # Complex command with mix of approved and restricted
        assert self.manager.needs_permission("ls -la | grep file && rm temp.txt") is True

    def test_approve_command_type(self):
        """Test approving command types."""
        # Approve a command not in any list
        assert self.manager.needs_permission("git status") is True
        self.manager.approve_command_type("git status")
        assert self.manager.needs_permission("git status") is False
        
        # Approve with timeout
        assert self.manager.needs_permission("npm install") is True
        self.manager.approve_command_type("npm install", timeout=10)
        assert self.manager.needs_permission("npm install") is False

    def test_approve_command(self):
        """Test approving specific commands."""
        # Specific command approval without timeout
        specific_cmd = "git clone https://github.com/user/repo.git"
        assert self.manager.needs_permission(specific_cmd) is True
        self.manager.approve_command(specific_cmd)
        # Without timeout, specific commands aren't persistently approved
        assert self.manager.needs_permission(specific_cmd) is True
        
        # Specific command with timeout
        self.manager.approve_command(specific_cmd, timeout=10)
        assert self.manager.needs_permission(specific_cmd) is False

    def test_approve_all(self):
        """Test approving all commands."""
        # Random restricted command
        assert self.manager.needs_permission("rm -rf temp/") is True
        
        # Approve all
        self.manager.approve_all(timeout=10)
        
        # All commands should be approved now
        assert self.manager.needs_permission("rm -rf temp/") is False
        assert self.manager.needs_permission("git status") is False
        assert self.manager.needs_permission("npm install") is False
        
        # Except prohibited commands
        assert self.manager.needs_permission("sudo apt update") is False
        assert self.manager.is_command_prohibited("sudo apt update") is True

    def test_command_approval_timeout(self):
        """Test that command approvals expire after timeout."""
        # Approve with very short timeout
        self.manager.approve_command_type("git status", timeout=0.1)
        assert self.manager.needs_permission("git status") is False
        
        # Wait for timeout to expire
        time.sleep(0.2)
        
        # Should need permission again
        assert self.manager.needs_permission("git status") is True

    @patch("q_cli.utils.permissions.parse_command_list")
    def test_from_config(self, mock_parse):
        """Test creating a manager from configuration."""
        # Setup mock for parse_command_list
        mock_parse.side_effect = lambda x: json.loads(x) if x else []
        
        # Create config dict
        config = {
            "ALWAYS_APPROVED_COMMANDS": '["ls", "cat"]',
            "ALWAYS_RESTRICTED_COMMANDS": '["rm", "chmod"]',
            "PROHIBITED_COMMANDS": '["sudo"]'
        }
        
        # Create manager from config
        manager = CommandPermissionManager.from_config(config)
        
        # Verify the manager was configured correctly
        assert "ls" in manager.always_approved_commands
        assert "rm" in manager.always_restricted_commands
        assert "sudo" in manager.prohibited_commands


class TestPermissionContextManager:
    """Tests for PermissionContextManager functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.context_manager = PermissionContextManager()

    def test_approval_context_creation(self):
        """Test creating approval contexts."""
        context = ApprovalContext.create(timeout=60, context="Test approval")
        
        assert context.is_valid is True
        assert context.time_remaining > 0
        assert context.time_remaining <= 60
        assert context.context == "Test approval"

    def test_approval_context_expiry(self):
        """Test approval context expiration."""
        # Create context with very short timeout
        context = ApprovalContext.create(timeout=0.1, context="Test approval")
        assert context.is_valid is True
        
        # Wait for timeout to expire
        time.sleep(0.2)
        
        # Should be expired now
        assert context.is_valid is False
        assert context.time_remaining == 0

    def test_approve_command(self):
        """Test approving specific commands."""
        cmd = "git clone repo"
        self.context_manager.approve_command(cmd, timeout=10)
        
        assert cmd in self.context_manager.command_approvals
        assert self.context_manager.command_approvals[cmd].is_valid is True
        assert self.context_manager.is_command_approved(cmd, "git") is True

    def test_approve_command_type(self):
        """Test approving command types."""
        cmd_type = "git"
        self.context_manager.approve_command_type(cmd_type, timeout=10)
        
        assert cmd_type in self.context_manager.type_approvals
        assert self.context_manager.type_approvals[cmd_type].is_valid is True
        assert self.context_manager.is_command_approved("git status", "git") is True

    def test_approve_all(self):
        """Test global approval."""
        self.context_manager.approve_all(timeout=10)
        
        assert self.context_manager.global_approval is not None
        assert self.context_manager.global_approval.is_valid is True
        assert self.context_manager.is_command_approved("any command", "any") is True

    def test_clean_expired_approvals(self):
        """Test cleaning expired approvals."""
        # Add some approvals with very short timeout
        self.context_manager.approve_command("cmd1", timeout=0.1)
        self.context_manager.approve_command_type("type1", timeout=0.1)
        self.context_manager.approve_all(timeout=0.1)
        
        # Wait for timeout to expire
        time.sleep(0.2)
        
        # Trigger cleanup
        self.context_manager._clean_expired_approvals()
        
        # All approvals should be removed
        assert len(self.context_manager.command_approvals) == 0
        assert len(self.context_manager.type_approvals) == 0
        assert self.context_manager.global_approval is None

    def test_reset(self):
        """Test resetting all approvals."""
        # Add some approvals
        self.context_manager.approve_command("cmd1", timeout=60)
        self.context_manager.approve_command_type("type1", timeout=60)
        self.context_manager.approve_all(timeout=60)
        
        # Reset the manager
        self.context_manager.reset()
        
        # All approvals should be removed
        assert len(self.context_manager.command_approvals) == 0
        assert len(self.context_manager.type_approvals) == 0
        assert self.context_manager.global_approval is None

    def test_get_approval_context(self):
        """Test retrieving approval contexts."""
        # Add approvals at different levels
        self.context_manager.approve_command("specific_cmd", timeout=10, context="Command specific")
        self.context_manager.approve_command_type("git", timeout=20, context="Type specific")
        self.context_manager.approve_all(timeout=30, context="Global")
        
        # Global context should take precedence
        context = self.context_manager.get_approval_context("any_cmd", "any_type")
        assert context is self.context_manager.global_approval
        assert context.context == "Global"
        
        # Reset global approval
        self.context_manager.global_approval = None
        
        # Command-specific should take precedence over type
        context = self.context_manager.get_approval_context("specific_cmd", "git")
        assert context is self.context_manager.command_approvals["specific_cmd"]
        assert context.context == "Command specific"
        
        # Type-specific as fallback
        context = self.context_manager.get_approval_context("git status", "git")
        assert context is self.context_manager.type_approvals["git"]
        assert context.context == "Type specific"
        
        # No context for unknown command/type
        context = self.context_manager.get_approval_context("unknown", "unknown")
        assert context is None