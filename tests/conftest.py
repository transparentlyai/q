"""Pytest configuration for Q CLI tests."""

import os
import sys
import pytest
from unittest.mock import MagicMock
from rich.console import Console

# Add the root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.fixture
def mock_console():
    """Create a mock console for testing."""
    console = MagicMock(spec=Console)
    return console


@pytest.fixture
def temp_env():
    """Create a temporary environment for tests that modify environment variables."""
    old_env = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(old_env)