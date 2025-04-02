"""Command permission context management for q_cli."""

import os
import time
from typing import Dict, Set, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class ApprovalContext:
    """Context for command approvals with time-based expirations."""
    # Time-based approval context
    approved_at: float = 0.0  # Timestamp when approval occurred
    expires_at: float = 0.0   # Timestamp when approval expires
    approved_by: str = ""     # User or method that approved this command
    context: str = ""         # The context in which approval was granted
    
    # Default approval timeout in seconds (30 minutes)
    DEFAULT_TIMEOUT: int = 30 * 60
    
    @property
    def is_valid(self) -> bool:
        """Check if the approval context is still valid."""
        return time.time() < self.expires_at
    
    @property
    def time_remaining(self) -> float:
        """Get the time remaining for this approval context."""
        if not self.is_valid:
            return 0.0
        return self.expires_at - time.time()
    
    @classmethod
    def create(cls, timeout: Optional[int] = None, context: str = "", approved_by: str = "user") -> "ApprovalContext":
        """Create a new approval context with the specified timeout."""
        now = time.time()
        timeout = timeout or cls.DEFAULT_TIMEOUT
        return cls(
            approved_at=now,
            expires_at=now + timeout,
            approved_by=approved_by,
            context=context
        )
    
    def refresh(self, timeout: Optional[int] = None) -> None:
        """Refresh the approval context with a new expiration time."""
        now = time.time()
        timeout = timeout or self.DEFAULT_TIMEOUT
        self.approved_at = now
        self.expires_at = now + timeout


class PermissionContextManager:
    """Manages command permissions with contextual time-based approvals."""
    
    def __init__(self):
        """Initialize the permission context manager."""
        # Maps command pattern to approval context
        self.command_approvals: Dict[str, ApprovalContext] = {}
        # Maps command type to approval context
        self.type_approvals: Dict[str, ApprovalContext] = {}
        # Global approval context (approve all)
        self.global_approval: Optional[ApprovalContext] = None
        
    def approve_command(self, command: str, timeout: Optional[int] = None, context: str = "") -> None:
        """Approve a specific command pattern with time-based expiration."""
        self.command_approvals[command] = ApprovalContext.create(
            timeout=timeout, 
            context=context,
            approved_by="user"
        )
        
    def approve_command_type(self, command_type: str, timeout: Optional[int] = None, context: str = "") -> None:
        """Approve a command type with time-based expiration."""
        self.type_approvals[command_type] = ApprovalContext.create(
            timeout=timeout, 
            context=context,
            approved_by="user"
        )
        
    def approve_all(self, timeout: Optional[int] = None, context: str = "") -> None:
        """Approve all commands with time-based expiration."""
        self.global_approval = ApprovalContext.create(
            timeout=timeout, 
            context=context,
            approved_by="user"
        )
        
    def is_command_approved(self, command: str, command_type: str) -> bool:
        """Check if a command is approved based on pattern, type, or global approval."""
        # Clean expired approvals first
        self._clean_expired_approvals()
        
        # Check global approval first
        if self.global_approval and self.global_approval.is_valid:
            return True
            
        # Check specific command pattern approval
        if command in self.command_approvals and self.command_approvals[command].is_valid:
            return True
            
        # Check command type approval
        if command_type in self.type_approvals and self.type_approvals[command_type].is_valid:
            return True
            
        return False
        
    def get_approval_context(self, command: str, command_type: str) -> Optional[ApprovalContext]:
        """Get the approval context for a command if it exists."""
        # Clean expired approvals first
        self._clean_expired_approvals()
        
        # Check global approval first
        if self.global_approval and self.global_approval.is_valid:
            return self.global_approval
            
        # Check specific command pattern approval
        if command in self.command_approvals and self.command_approvals[command].is_valid:
            return self.command_approvals[command]
            
        # Check command type approval
        if command_type in self.type_approvals and self.type_approvals[command_type].is_valid:
            return self.type_approvals[command_type]
            
        return None
        
    def _clean_expired_approvals(self) -> None:
        """Clean up expired approvals."""
        # Check global approval
        if self.global_approval and not self.global_approval.is_valid:
            self.global_approval = None
            
        # Remove expired command pattern approvals
        self.command_approvals = {
            cmd: context for cmd, context in self.command_approvals.items() 
            if context.is_valid
        }
        
        # Remove expired command type approvals
        self.type_approvals = {
            cmd_type: context for cmd_type, context in self.type_approvals.items() 
            if context.is_valid
        }
        
    def reset(self) -> None:
        """Reset all approvals."""
        self.command_approvals.clear()
        self.type_approvals.clear()
        self.global_approval = None