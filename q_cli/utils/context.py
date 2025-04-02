"""Context management utilities for Q."""

import os
import tiktoken
import time
from typing import Dict, List, Optional, Tuple, Union, Deque
import re
from collections import deque

from rich.console import Console

from q_cli.utils.constants import (
    get_debug,
    DEFAULT_MAX_CONTEXT_TOKENS,
    DEFAULT_CONTEXT_PRIORITY_MODE,
    ESSENTIAL_PRIORITY,
    IMPORTANT_PRIORITY,
    SUPPLEMENTARY_PRIORITY,
    ESSENTIAL_TOKEN_ALLOCATION,
    IMPORTANT_TOKEN_ALLOCATION,
    SUPPLEMENTARY_TOKEN_ALLOCATION,
)


def num_tokens_from_string(string_or_obj: Union[str, Dict, List], encoding_name: str = "cl100k_base") -> int:
    """
    Return the number of tokens in a text string or message object.
    
    Args:
        string_or_obj: Text string or message object (dict with content field, or list of messages)
        encoding_name: Tiktoken encoding name to use
        
    Returns:
        Estimated token count
    """
    try:
        encoding = tiktoken.get_encoding(encoding_name)
        
        # Handle different input types
        if isinstance(string_or_obj, str):
            # Simple string case
            return len(encoding.encode(string_or_obj))
        
        elif isinstance(string_or_obj, dict):
            # Message dict case
            if "content" in string_or_obj:
                content = string_or_obj["content"]
                
                # Handle multimodal content
                if isinstance(content, list):
                    total_tokens = 0
                    for item in content:
                        if isinstance(item, dict):
                            if item.get("type") == "text":
                                total_tokens += len(encoding.encode(item.get("text", "")))
                            elif item.get("type") == "image":
                                # Image tokens are harder to estimate, use rough approximation
                                # Claude's current rate: ~170 tokens per 512x512 image
                                # This is a very rough estimate
                                total_tokens += 700  # Conservative estimate for typical image
                    return total_tokens
                else:
                    # Standard text content
                    return len(encoding.encode(str(content)))
            return 0
        
        elif isinstance(string_or_obj, list):
            # List of messages case
            return sum(num_tokens_from_string(msg) for msg in string_or_obj)
        
        else:
            # Fallback to string representation
            return len(encoding.encode(str(string_or_obj)))
        
    except Exception:
        # Fallback to a simple approximation if tiktoken fails
        if isinstance(string_or_obj, str):
            return len(string_or_obj) // 4  # Rough approximation
        elif isinstance(string_or_obj, dict) and "content" in string_or_obj:
            content = string_or_obj["content"]
            if isinstance(content, list):
                # Rougher approximation for multimodal
                text_chars = sum(len(item.get("text", "")) for item in content 
                               if isinstance(item, dict) and item.get("type") == "text")
                image_count = sum(1 for item in content 
                                if isinstance(item, dict) and item.get("type") == "image")
                return (text_chars // 4) + (image_count * 700)
            return len(str(content)) // 4
        elif isinstance(string_or_obj, list):
            # Recursively apply to list items
            return sum(num_tokens_from_string(item) for item in string_or_obj)
        return len(str(string_or_obj)) // 4  # Very rough approximation


class ContextItem:
    """A single item of context with priority and token information."""

    def __init__(self, content: str, priority: str, description: str = ""):
        """
        Initialize a context item.

        Args:
            content: The actual content of this context item
            priority: Priority level (essential, important, supplementary)
            description: Optional description of this context item
        """
        self.content = content
        self.priority = priority
        self.description = description
        self.token_count = num_tokens_from_string(content)

    def __str__(self) -> str:
        return f"{self.description} ({self.token_count} tokens, {self.priority})"


class ContextManager:
    """
    Manages context for AI conversations with token counting and prioritization.

    This class handles:
    - Token counting for all context items
    - Prioritization of context by importance
    - Context pruning when limits are approached
    - Different priority modes for different use cases
    """

    def __init__(
        self,
        max_tokens: Optional[int] = None,
        priority_mode: str = DEFAULT_CONTEXT_PRIORITY_MODE,
        console: Optional[Console] = None,
    ):
        """
        Initialize the context manager.

        Args:
            max_tokens: Maximum tokens for context
            priority_mode: Priority mode (balanced, code, conversation)
            console: Console for output
        """
        self.max_tokens = (
            max_tokens if max_tokens is not None else DEFAULT_MAX_CONTEXT_TOKENS
        )
        self.priority_mode = priority_mode
        self.console = console or Console()

        # Dictionary of context items by priority level
        self.context_items: Dict[str, List[ContextItem]] = {
            ESSENTIAL_PRIORITY: [],
            IMPORTANT_PRIORITY: [],
            SUPPLEMENTARY_PRIORITY: [],
        }

        # Token allocations by priority (can be adjusted based on priority_mode)
        self.token_allocations = self._get_token_allocations()

        # System prompt (stored separately as it's always included)
        self.system_prompt: Optional[str] = None
        self.system_prompt_tokens = (
            0  # Initialize to 0, will be updated when prompt is set
        )

    def _get_token_allocations(self) -> Dict[str, float]:
        """
        Get token allocations based on priority mode.

        Returns:
            Dictionary of token allocations by priority
        """
        # Default allocations
        allocations = {
            ESSENTIAL_PRIORITY: ESSENTIAL_TOKEN_ALLOCATION,
            IMPORTANT_PRIORITY: IMPORTANT_TOKEN_ALLOCATION,
            SUPPLEMENTARY_PRIORITY: SUPPLEMENTARY_TOKEN_ALLOCATION,
        }

        # Adjust based on priority mode
        if self.priority_mode == "code":
            # Favor code context
            allocations[IMPORTANT_PRIORITY] = 0.50
            allocations[SUPPLEMENTARY_PRIORITY] = 0.20
        elif self.priority_mode == "conversation":
            # Favor conversation history
            allocations[ESSENTIAL_PRIORITY] = 0.40
            allocations[SUPPLEMENTARY_PRIORITY] = 0.20

        return allocations

    def add_context(self, content: str, priority: str, description: str = "") -> None:
        """
        Add a context item with specified priority.

        Args:
            content: The content to add
            priority: Priority level
            description: Optional description
        """
        if not content:
            return

        if priority not in self.context_items:
            if get_debug():
                self.console.print(
                    f"[yellow]Invalid priority: {priority}, using supplementary[/yellow]"
                )
            priority = SUPPLEMENTARY_PRIORITY

        item = ContextItem(content, priority, description)
        self.context_items[priority].append(item)

        if get_debug():
            self.console.print(
                f"[info]Added {description} context: {item.token_count} tokens[/info]"
            )

    def set_system_prompt(self, prompt: str) -> None:
        """
        Set the system prompt (highest priority content).

        Args:
            prompt: The system prompt to set
        """
        self.system_prompt = prompt
        self.system_prompt_tokens = num_tokens_from_string(prompt)

        if get_debug():
            self.console.print(
                f"[info]System prompt: {self.system_prompt_tokens} tokens[/info]"
            )

    def get_total_tokens(self) -> int:
        """
        Get the total number of tokens across all context items.

        Returns:
            Total token count
        """
        total = self.system_prompt_tokens

        for priority, items in self.context_items.items():
            for item in items:
                total += item.token_count

        return total

    def get_tokens_by_priority(self) -> Dict[str, int]:
        """
        Get token counts broken down by priority level.

        Returns:
            Dictionary of token counts by priority
        """
        counts = {
            "system": self.system_prompt_tokens,
            ESSENTIAL_PRIORITY: 0,
            IMPORTANT_PRIORITY: 0,
            SUPPLEMENTARY_PRIORITY: 0,
        }

        for priority, items in self.context_items.items():
            for item in items:
                counts[priority] += item.token_count

        return counts

    def get_allocated_tokens(self, priority: str) -> int:
        """
        Get the number of tokens allocated to a priority level.

        Args:
            priority: Priority level

        Returns:
            Token allocation for the priority level
        """
        # System prompt is always fully allocated
        if priority == "system":
            return self.system_prompt_tokens

        # For other priorities, calculate based on percentage allocation
        return int(self.max_tokens * self.token_allocations[priority])

    def _trim_context_items(
        self, priority: str, target_tokens: int
    ) -> List[ContextItem]:
        """
        Trim context items to fit within target token count.

        Args:
            priority: Priority level to trim
            target_tokens: Target token count

        Returns:
            List of trimmed context items
        """
        items = self.context_items[priority]

        # Nothing to trim if we're under target
        current_tokens = sum(item.token_count for item in items)
        if current_tokens <= target_tokens:
            return items

        # Sort items by token count in descending order
        # For supplementary items, we'll cut the largest ones first
        # For essential/important items, we'll trim from the oldest
        if priority == SUPPLEMENTARY_PRIORITY:
            sorted_items = sorted(items, key=lambda x: x.token_count, reverse=True)
        else:
            # Keep the most recent items (assumes items were added in chronological order)
            sorted_items = items.copy()

        # Keep adding items until we hit the target
        result: list[ContextItem] = []
        total_tokens = 0

        for item in reversed(sorted_items):
            if total_tokens + item.token_count <= target_tokens:
                result.insert(0, item)  # Insert at beginning to maintain order
                total_tokens += item.token_count
            else:
                # For essential items, we might need to truncate content rather than skip
                if priority == ESSENTIAL_PRIORITY:
                    # Try to include a truncated version if it's a large item
                    if item.token_count > 100:
                        # Estimate roughly how much we can keep
                        keep_ratio = (target_tokens - total_tokens) / item.token_count
                        if keep_ratio > 0.5:  # Only truncate if we can keep most of it
                            truncated_content = truncate_text_to_tokens(
                                item.content, target_tokens - total_tokens
                            )
                            truncated_item = ContextItem(
                                truncated_content,
                                item.priority,
                                f"{item.description} (truncated)",
                            )
                            result.insert(0, truncated_item)
                            total_tokens += truncated_item.token_count

                if get_debug():
                    self.console.print(
                        f"[yellow]Dropping {item.description} to fit token limit[/yellow]"
                    )

        if get_debug() and len(result) < len(items):
            dropped = len(items) - len(result)
            self.console.print(
                f"[yellow]Dropped {dropped} items from {priority} priority[/yellow]"
            )

        return result

    def optimize_context(self) -> None:
        """
        Optimize context to stay within token limits.
        This trims lower priority content first.
        """
        # We need both max_tokens and a valid system_prompt_tokens value
        if self.max_tokens is None:
            self.max_tokens = DEFAULT_MAX_CONTEXT_TOKENS
            if get_debug():
                self.console.print(
                    f"[yellow]Using default max tokens: {self.max_tokens}[/yellow]"
                )

        token_budget = self.max_tokens - self.system_prompt_tokens
        if token_budget <= 0:
            # System prompt alone exceeds token limit
            if get_debug():
                self.console.print(
                    f"[red]Warning: System prompt alone exceeds token limit[/red]"
                )
            return

        # Calculate target tokens for each priority based on allocations
        essential_target = min(
            int(token_budget * self.token_allocations[ESSENTIAL_PRIORITY]),
            sum(item.token_count for item in self.context_items[ESSENTIAL_PRIORITY]),
        )

        # Reclaim unused essential tokens for important
        remaining_budget = token_budget - essential_target
        important_target = min(
            int(remaining_budget * 0.7),  # Give 70% of remaining to important
            sum(item.token_count for item in self.context_items[IMPORTANT_PRIORITY]),
        )

        # Give the rest to supplementary
        supplementary_target = min(
            remaining_budget - important_target,
            sum(
                item.token_count for item in self.context_items[SUPPLEMENTARY_PRIORITY]
            ),
        )

        # Trim each priority level to fit targets
        self.context_items[ESSENTIAL_PRIORITY] = self._trim_context_items(
            ESSENTIAL_PRIORITY, essential_target
        )
        self.context_items[IMPORTANT_PRIORITY] = self._trim_context_items(
            IMPORTANT_PRIORITY, important_target
        )
        self.context_items[SUPPLEMENTARY_PRIORITY] = self._trim_context_items(
            SUPPLEMENTARY_PRIORITY, supplementary_target
        )

        if get_debug():
            total_after = sum(
                sum(item.token_count for item in items)
                for items in self.context_items.values()
            )
            self.console.print(f"[info]Optimized context: {total_after} tokens[/info]")

    def build_context_string(self) -> str:
        """
        Build the final context string from all items.

        Returns:
            The combined context string
        """
        # Check if we have any context items before optimizing
        total_items = sum(len(items) for items in self.context_items.values())

        # Only optimize if we have context to optimize
        if total_items > 0:
            self.optimize_context()

        context_parts = []

        # Add items from each priority level in order
        for priority in [
            ESSENTIAL_PRIORITY,
            IMPORTANT_PRIORITY,
            SUPPLEMENTARY_PRIORITY,
        ]:
            for item in self.context_items[priority]:
                if item.content:
                    context_parts.append(item.content)

        # Join with double newlines
        return "\n\n".join(context_parts)
        
    def get_current_context(self) -> str:
        """
        Get the current optimized context string.
        
        Returns:
            The combined context string without re-optimizing
        """
        return self.build_context_string()


def truncate_text_to_tokens(text: str, max_tokens: int) -> str:
    """
    Truncate text to fit within max_tokens.

    Args:
        text: The text to truncate
        max_tokens: Maximum token count

    Returns:
        Truncated text
    """
    if num_tokens_from_string(text) <= max_tokens:
        return text

    # For code blocks, preserve the start and end
    if "```" in text:
        # Split by code blocks
        parts = re.split(r"(```.*?```)", text, flags=re.DOTALL)
        result_parts = []
        tokens_used = 0

        # Keep adding parts until we hit the limit
        for part in parts:
            part_tokens = num_tokens_from_string(part)
            if tokens_used + part_tokens <= max_tokens:
                result_parts.append(part)
                tokens_used += part_tokens
            else:
                # For the last part, truncate it
                remaining = max_tokens - tokens_used
                if remaining > 20:  # Only add if we have reasonable space
                    # If it's a code block, preserve opening and closing
                    if part.startswith("```"):
                        # Extract language and opening marker
                        lines = part.split("\n")
                        if len(lines) > 2:
                            opening = lines[0]
                            # Approximate token count for truncated content
                            content_tokens = remaining - num_tokens_from_string(
                                opening + "\n```"
                            )
                            if content_tokens > 10:
                                truncated = truncate_text_to_tokens(
                                    "\n".join(lines[1:-1]), content_tokens
                                )
                                result_parts.append(f"{opening}\n{truncated}\n```")
                    else:
                        # For regular text, just truncate
                        truncated = simple_truncate(part, remaining)
                        result_parts.append(truncated)
                break

        return "".join(result_parts)

    # For plain text, simpler approach
    return simple_truncate(text, max_tokens)


def simple_truncate(text: str, max_tokens: int) -> str:
    """
    Simple truncation for plain text.

    Args:
        text: Text to truncate
        max_tokens: Maximum token count

    Returns:
        Truncated text
    """
    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(text)

    if len(tokens) <= max_tokens:
        return text

    # Keep first 70% and last 30% if possible
    if max_tokens > 20:
        first_portion = int(max_tokens * 0.7)
        last_portion = max_tokens - first_portion - 3  # 3 tokens for ellipsis

        if last_portion > 5:
            first_part = encoding.decode(tokens[:first_portion])
            last_part = encoding.decode(tokens[-last_portion:])
            return f"{first_part}...\n[content truncated]\n...{last_part}"

    # Simple truncation if we can't do the above
    return encoding.decode(tokens[: max_tokens - 3]) + "..."


class TokenRateTracker:
    """
    Tracks token usage rate for API rate limiting compliance.
    
    Maintains a sliding window of token usage to ensure we don't exceed
    the provider-specific rate limit tokens per minute.
    When max_tokens_per_min is not defined or set to 0, rate limiting is disabled.
    """
    
    def __init__(self, max_tokens_per_min: int = 80000):
        """
        Initialize the token rate tracker.
        
        Args:
            max_tokens_per_min: Maximum tokens allowed per minute. If None or 0, rate limiting is disabled.
        """
        self.max_tokens_per_min = max_tokens_per_min
        self.window_size = 60  # 1 minute in seconds
        # Store (timestamp, token_count) tuples
        self.usage_window: Deque[Tuple[float, int]] = deque()
        self.total_tokens_in_window = 0
    
    def add_usage(self, token_count: int, timestamp: float = None) -> None:
        """
        Record token usage at the current time or specified timestamp.
        Does nothing if rate limiting is disabled.
        
        Args:
            token_count: Number of tokens used
            timestamp: Optional specific timestamp to use (e.g., after API response completion)
        """
        # Skip tracking if rate limiting is disabled
        if not self.max_tokens_per_min:
            return
            
        current_time = timestamp if timestamp is not None else time.time()
        
        # First clean up expired entries older than our window
        self._clean_expired_entries(current_time)
        
        # Add the new usage
        self.usage_window.append((current_time, token_count))
        self.total_tokens_in_window += token_count
    
    def _clean_expired_entries(self, current_time: float) -> None:
        """
        Remove entries older than the window size.
        
        Args:
            current_time: Current timestamp
        """
        window_start = current_time - self.window_size
        
        # Remove expired entries
        while self.usage_window and self.usage_window[0][0] < window_start:
            timestamp, tokens = self.usage_window.popleft()
            self.total_tokens_in_window -= tokens
    
    def get_current_usage(self) -> int:
        """
        Get the current token usage within the time window.
        
        Returns:
            Total tokens used in the current window
            Returns 0 when rate limiting is disabled
        """
        if not self.max_tokens_per_min:
            return 0
            
        self._clean_expired_entries(time.time())
        return self.total_tokens_in_window
    
    def can_use_tokens(self, token_count: int) -> bool:
        """
        Check if the specified token count can be used without exceeding the rate limit.
        
        Args:
            token_count: Number of tokens to check
            
        Returns:
            True if tokens can be used, False if it would exceed rate limit
            Always returns True when rate limiting is disabled (max_tokens_per_min is None or 0)
        """
        if not self.max_tokens_per_min:
            return True
            
        current_usage = self.get_current_usage()
        return (current_usage + token_count) <= self.max_tokens_per_min
    
    def wait_if_needed(self, token_count: int, console: Optional[Console] = None) -> float:
        """
        Wait if necessary to avoid exceeding rate limits when using token_count tokens.
        
        Args:
            token_count: Number of tokens that will be used
            console: Optional console for logging
            
        Returns:
            Seconds waited (0 if no wait was needed)
            Always returns 0 when rate limiting is disabled (max_tokens_per_min is None or 0)
        """
        # Skip rate limiting entirely if disabled
        if not self.max_tokens_per_min:
            return 0.0
            
        current_time = time.time()
        self._clean_expired_entries(current_time)
        
        # Special case for very large requests (>70% of rate limit)
        # For these, we want to be extra cautious to avoid rate limit errors
        large_request_threshold = int(self.max_tokens_per_min * 0.7)
        
        if token_count > large_request_threshold:
            # For very large requests, we need to be more conservative
            # Wait until we have enough capacity, which may require waiting
            # for most/all previous requests to expire
            capacity_needed = token_count
            
            if self.total_tokens_in_window > (self.max_tokens_per_min - capacity_needed):
                if console:
                    console.print(f"[yellow]Large request ({token_count} tokens) detected. Ensuring sufficient capacity...[/yellow]")
                
                # For very large requests, wait until we're close to empty
                if self.usage_window:
                    oldest_timestamp = self.usage_window[0][0]
                    wait_time = max(0, (oldest_timestamp + self.window_size) - current_time)
                    
                    if wait_time > 0:
                        if console:
                            console.print(f"[yellow]Waiting {wait_time:.1f} seconds to ensure sufficient capacity for large request...[/yellow]")
                        time.sleep(wait_time)
                        # Clean up again after waiting
                        self._clean_expired_entries(time.time())
                        return wait_time
        
        # Standard case: if adding these tokens would exceed our limit, calculate wait time
        elif (self.total_tokens_in_window + token_count) > self.max_tokens_per_min:
            # Calculate how long to wait for enough tokens to expire
            tokens_to_expire = (self.total_tokens_in_window + token_count) - self.max_tokens_per_min
            
            # Find the earliest entries that sum to tokens_to_expire
            tokens_found = 0
            earliest_timestamp = current_time
            
            for timestamp, tokens in self.usage_window:
                tokens_found += tokens
                if tokens_found >= tokens_to_expire:
                    earliest_timestamp = timestamp
                    break
            
            # Calculate wait time until those tokens expire from our window
            wait_time = max(0, (earliest_timestamp + self.window_size) - current_time)
            
            if wait_time > 0:
                if console:
                    console.print(f"[yellow]Rate limit approaching. Waiting {wait_time:.1f} seconds before continuing...[/yellow]")
                time.sleep(wait_time)
                # Clean up again after waiting
                self._clean_expired_entries(time.time())
                return wait_time
        
        return 0.0
