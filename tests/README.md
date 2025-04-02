# Q CLI Tests

This directory contains tests for the Q CLI project. The tests are built using `pytest` and focus on core functionality like command processing, permission management, and file operations.

## Running Tests

You can run the tests using the provided script:

```bash
# From the project root
./scripts/run_tests.sh
```

Or run pytest directly:

```bash
# Run all tests
python -m pytest -xvs tests/

# Run specific test modules
python -m pytest -xvs tests/utils/test_commands.py
python -m pytest -xvs tests/utils/test_permissions.py

# Run specific test class
python -m pytest -xvs tests/utils/test_commands.py::TestCommandConfirmation
```

## Test Structure

The tests are organized by module and functionality:

- `tests/utils/test_commands.py`: Tests for command execution, user interaction, dangerous command detection, command marker extraction, and file operations
- `tests/utils/test_permissions.py`: Tests for permission management, command approval hierarchy, time-based approvals, and contextual approvals
- `tests/utils/test_provider_factory.py`: Tests for different model providers (Anthropic, VertexAI, Groq, OpenAI), provider configuration, and provider factory functionality
- `tests/utils/test_client.py`: Tests for the LLM client, message transformation, and API interactions

## Adding New Tests

When adding new tests, follow these guidelines:

1. Organize tests by functionality into logical classes
2. Use appropriate fixtures from `conftest.py` 
3. Mock external dependencies and file I/O operations
4. Each test should focus on testing a single aspect of functionality
5. Follow the existing naming conventions: `test_feature_expected_behavior`

## Notes on Testing

- File operations tests skip complex security validation that would require extensive mocking
- Commands that interact with the file system are mocked to avoid actual file system changes
- Time-based tests use short durations to prevent long test runs