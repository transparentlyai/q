#!/bin/bash
# Simple script to run all tests for the Q CLI project

set -e  # Exit on error

# Display banner
echo "========================================"
echo "  Running tests for Q CLI Project"
echo "========================================"

# Set environment variables
export PYTHONPATH="$PYTHONPATH:$(pwd)"

# Ensure script is run from project root
if [ ! -d "q_cli" ]; then
    echo "Error: This script must be run from the project root directory"
    echo "Current directory: $(pwd)"
    echo "Please run: cd /path/to/q && ./scripts/run_tests.sh"
    exit 1
fi

# Run linting
echo -e "\n[1/3] Running linting checks..."
flake8 q.py q_cli tests || echo "WARNING: Linting issues found"

# Run type checking
echo -e "\n[2/3] Running type checking..."
mypy q.py || echo "WARNING: Type checking issues found"

# Run tests with pytest
echo -e "\n[3/3] Running pytest tests..."
python3 -m pytest -xvs tests/

# Run model-specific tests
echo -e "\n[3/3.1] Running model-specific tests..."
python3 -m pytest -xvs tests/utils/test_provider_factory.py
python3 -m pytest -xvs tests/utils/test_client.py

# Display summary
echo -e "\n========================================"
echo "  Test run complete"
echo "========================================"