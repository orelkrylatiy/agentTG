"""
Agent module data models.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AgentAction(str, Enum):
    """Types of agent actions."""

    IGNORE = "ignore"
    NOTIFY = "notify"
    DRAFT = "draft"
    AUTO_REPLY = "auto_reply"


@dataclass
class AgentDecision:
    """Decision made by the agent for a message."""

    action: AgentAction
    reply_text: str | None = None
    requires_approval: bool = False
    reason: str = ""


@dataclass
class MessageContext:
    """Context for processing a message."""

    chat_id: int
    message_id: int
    sender_id: int
    sender_name: str | None
    text: str
    timestamp: datetime
    is_reply: bool = False
    reply_to_message_id: int | None = None
