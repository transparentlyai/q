"""Context management configuration for q_cli."""

import os
from typing import Dict


# Context system constants
DEFAULT_MAX_CONTEXT_TOKENS = 200000
DEFAULT_CONTEXT_PRIORITY_MODE = "balanced"

# Context priority levels
ESSENTIAL_PRIORITY = "essential"  # Must include, highest priority
IMPORTANT_PRIORITY = "important"  # Include if space available
SUPPLEMENTARY_PRIORITY = "supplementary"  # Include only if extra space

# Default token allocation by priority (percentages)
ESSENTIAL_TOKEN_ALLOCATION = 0.30  # 30% for essential context
IMPORTANT_TOKEN_ALLOCATION = 0.40  # 40% for important context
SUPPLEMENTARY_TOKEN_ALLOCATION = 0.30  # 30% for supplementary context

# File tree inclusion settings
INCLUDE_FILE_TREE = False  # Default setting, can be overridden by config

# History settings
MAX_HISTORY_TURNS = 20  # Maximum conversation turns to keep
HISTORY_PATH = os.path.expanduser("~/.q_history")  # Path to history file


# Debug mode
def get_debug() -> bool:
    """Get the DEBUG value from environment, respecting any recent changes.
    
    Returns:
        True if debug mode is enabled, False otherwise
    """
    debug_val = os.environ.get("Q_DEBUG", "false").lower()
    return debug_val in ["true", "1", "yes", "y", "on"]


def get_priority_mode_allocations(mode: str) -> Dict[str, float]:
    """Get token allocations based on priority mode.
    
    Args:
        mode: The priority mode (balanced, code, conversation)
        
    Returns:
        Dictionary of token allocations by priority level
    """
    # Default allocations
    allocations = {
        ESSENTIAL_PRIORITY: ESSENTIAL_TOKEN_ALLOCATION,
        IMPORTANT_PRIORITY: IMPORTANT_TOKEN_ALLOCATION,
        SUPPLEMENTARY_PRIORITY: SUPPLEMENTARY_TOKEN_ALLOCATION,
    }
    
    # Adjust based on priority mode
    if mode == "code":
        # Favor code context
        allocations[IMPORTANT_PRIORITY] = 0.50
        allocations[SUPPLEMENTARY_PRIORITY] = 0.20
    elif mode == "conversation":
        # Favor conversation history
        allocations[ESSENTIAL_PRIORITY] = 0.40
        allocations[SUPPLEMENTARY_PRIORITY] = 0.20
    
    return allocations