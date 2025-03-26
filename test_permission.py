#!/usr/bin/env python3
"""
Test script for command permission checking.
"""

from q_cli.utils.permissions import CommandPermissionManager

def test_permission_checking():
    """Test the enhanced permission checking for complex commands."""
    # Create a permission manager with 'rm' as a prohibited command
    pm = CommandPermissionManager(prohibited=["rm"])
    
    # Test cases with expected results
    test_cases = [
        ("Simple command", "echo hello", False),
        ("Simple rm command", "rm -rf /tmp", True),
        ("Command chain with rm", "echo hello && rm -rf /tmp", True),
        ("Find with exec rm", "find . -name \"__pycache__\" -type d -exec rm -rf {} \\;", True),
        ("Complex command chain", "find . -name \"__pycache__\" -type d -exec rm -rf {} + && echo done", True),
        ("Subshell with rm", "echo $(rm -rf /tmp)", True),
        ("Backtick with rm", "echo `rm -rf /tmp`", True),
        ("Raw backtick test", "`rm -rf /tmp`", True),
        ("Pipe with grep", "ls -la | grep .py", False),
    ]
    
    # Run the tests
    print("Testing prohibition detection:")
    print("-" * 50)
    for description, command, expected in test_cases:
        result = pm.is_command_prohibited(command)
        status = "✓" if result == expected else "✗"
        print(f"{status} {description}: {command}")
        if result != expected:
            print(f"   Expected: {expected}, Got: {result}")
    
    print("\nExtracted command types:")
    print("-" * 50)
    for description, command, _ in test_cases:
        cmd_types = pm.extract_all_command_types(command)
        print(f"{description}: {cmd_types}")

if __name__ == "__main__":
    test_permission_checking()