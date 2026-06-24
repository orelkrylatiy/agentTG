"""
Database models using SQLModel.
"""

from dataclasses import dataclass, field as dataclass_field
from datetime import datetime
from enum import Enum

try:
    from sqlmodel import Field, SQLModel
    model_dataclass = lambda cls: cls
except ImportError:  # pragma: no cover
    def Field(default=None, **kwargs):
        if "default_factory" in kwargs:
            return dataclass_field(default_factory=kwargs["default_factory"])
        return default

    class SQLModel:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()

    model_dataclass = dataclass


class ChatMode(str, Enum):
    """Chat processing modes."""

    OFF = "OFF"  # Do nothing
    WATCH = "WATCH"  # Only notify owner
    DRAFT = "DRAFT"  # Generate draft for approval
    AUTO = "AUTO"  # Auto-reply (trusted chats only)


class MessageDirection(str, Enum):
    """Message direction in logs."""

    INCOMING = "incoming"
    OUTGOING = "outgoing"
    DRAFT = "draft"
    AGENT_SENT = "agent_sent"


class ActionStatus(str, Enum):
    """Pending action status."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    EXPIRED = "expired"


@model_dataclass
class ChatSettings(SQLModel, table=True):
    """Settings for individual chats."""

    __tablename__ = "chat_settings"

    id: int | None = Field(default=None, primary_key=True)
    chat_id: int = Field(..., unique=True, index=True)
    chat_title: str | None = Field(default=None)
    mode: ChatMode = Field(default=ChatMode.OFF)
    is_trusted: bool = Field(default=False)
    last_incoming_message_id: int | None = Field(default=None)
    last_agent_reply_at: datetime | None = Field(default=None)
    paused_until: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


@model_dataclass
class MessageLog(SQLModel, table=True):
    """Log of all messages processed by the agent."""

    __tablename__ = "message_log"

    id: int | None = Field(default=None, primary_key=True)
    chat_id: int = Field(..., index=True)
    message_id: int = Field(..., index=True)
    sender_id: int | None = Field(default=None)
    direction: MessageDirection = Field(...)
    text: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


@model_dataclass
class PendingAction(SQLModel, table=True):
    """Actions pending owner approval."""

    __tablename__ = "pending_actions"

    id: int | None = Field(default=None, primary_key=True)
    action_type: str = Field(...)  # reply, send_message
    chat_id: int = Field(..., index=True)
    reply_to_message_id: int | None = Field(default=None)
    text: str = Field(...)
    status: ActionStatus = Field(default=ActionStatus.PENDING)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    decided_at: datetime | None = Field(default=None)
    executed_message_id: int | None = Field(default=None)


@model_dataclass
class GlobalState(SQLModel, table=True):
    """Global agent state key-value store."""

    __tablename__ = "global_state"

    key: str = Field(..., primary_key=True)
    value: str = Field(...)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
