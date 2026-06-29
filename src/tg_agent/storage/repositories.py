"""
Database repositories for data access.
"""

from datetime import datetime
from typing import Any

try:
    from sqlmodel import Session, select
    from sqlmodel.ext.asyncio.session import AsyncSession
except ImportError:  # pragma: no cover
    Session = Any
    AsyncSession = Any

    class _SelectStub:
        def where(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def limit(self, *args, **kwargs):
            return self

    def select(*args, **kwargs):
        return _SelectStub()

from tg_agent.logging import get_logger
from tg_agent.storage.models import (
    ActionStatus,
    ChatMode,
    ChatSettings,
    GlobalState,
    MessageDirection,
    MessageLog,
    MonitoredChannel,
    PendingAction,
)

logger = get_logger(__name__)


class ChatSettingsRepo:
    """Repository for chat settings."""

    def __init__(self, session: Session | AsyncSession):
        self.session = session

    def get_by_chat_id(self, chat_id: int) -> ChatSettings | None:
        """Get chat settings by chat ID."""
        statement = select(ChatSettings).where(ChatSettings.chat_id == chat_id)
        return self.session.exec(statement).first()

    def get_or_create(
        self,
        chat_id: int,
        default_mode: ChatMode = ChatMode.OFF,
        chat_title: str | None = None,
    ) -> ChatSettings:
        """Get existing settings or create new with defaults."""
        settings = self.get_by_chat_id(chat_id)
        if settings is None:
            settings = ChatSettings(
                chat_id=chat_id,
                mode=default_mode,
                is_trusted=False,
                chat_title=chat_title,
            )
            self.session.add(settings)
            self.session.commit()
            self.session.refresh(settings)
            logger.info(f"Created new chat settings for {chat_id}")
        elif chat_title and settings.chat_title != chat_title:
            settings.chat_title = chat_title
            settings.updated_at = datetime.utcnow()
            self.session.commit()
            self.session.refresh(settings)
        return settings

    def update_mode(self, chat_id: int, mode: ChatMode) -> ChatSettings:
        """Update chat mode."""
        settings = self.get_or_create(chat_id)
        settings.mode = mode
        settings.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(settings)
        logger.info(f"Updated chat {chat_id} mode to {mode.value}")
        return settings

    def set_trusted(self, chat_id: int, trusted: bool = True) -> ChatSettings:
        """Set chat trusted status."""
        settings = self.get_or_create(chat_id)
        settings.is_trusted = trusted
        settings.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(settings)
        logger.info(f"Set chat {chat_id} trusted={trusted}")
        return settings

    def update_last_message(self, chat_id: int, message_id: int) -> None:
        """Update last incoming message ID for a chat."""
        settings = self.get_or_create(chat_id)
        settings.last_incoming_message_id = message_id
        settings.updated_at = datetime.utcnow()
        self.session.commit()

    def update_last_agent_reply(self, chat_id: int, replied_at: datetime | None = None) -> None:
        """Update the last agent reply timestamp."""
        settings = self.get_or_create(chat_id)
        settings.last_agent_reply_at = replied_at or datetime.utcnow()
        settings.updated_at = datetime.utcnow()
        self.session.commit()

    def set_paused_until(self, chat_id: int, until: datetime | None) -> None:
        """Set pause until time for a chat."""
        settings = self.get_or_create(chat_id)
        settings.paused_until = until
        settings.updated_at = datetime.utcnow()
        self.session.commit()

    def get_all(self) -> list[ChatSettings]:
        """Get all chat settings."""
        return list(self.session.exec(select(ChatSettings)).all())

    def get_by_mode(self, mode: ChatMode) -> list[ChatSettings]:
        """Get all chats with specific mode."""
        return list(self.session.exec(select(ChatSettings).where(ChatSettings.mode == mode)).all())


class MessageLogRepo:
    """Repository for message logs."""

    def __init__(self, session: Session | AsyncSession):
        self.session = session

    def create(
        self,
        chat_id: int,
        message_id: int,
        direction: MessageDirection,
        sender_id: int | None = None,
        text: str | None = None,
    ) -> MessageLog:
        """Create a new message log entry."""
        log_entry = MessageLog(
            chat_id=chat_id,
            message_id=message_id,
            sender_id=sender_id,
            direction=direction,
            text=text,
        )
        self.session.add(log_entry)
        self.session.commit()
        self.session.refresh(log_entry)
        return log_entry

    def exists(
        self,
        chat_id: int,
        message_id: int,
        direction: MessageDirection | None = None,
    ) -> bool:
        """Return True if a matching message log entry already exists."""
        statement = select(MessageLog).where(
            MessageLog.chat_id == chat_id,
            MessageLog.message_id == message_id,
        )
        if direction is not None:
            statement = statement.where(MessageLog.direction == direction)
        return self.session.exec(statement.limit(1)).first() is not None

    def get_recent(self, chat_id: int, limit: int = 10) -> list[MessageLog]:
        """Get recent messages for a chat."""
        statement = select(MessageLog).order_by(MessageLog.created_at.desc()).limit(limit)
        if chat_id:
            statement = statement.where(MessageLog.chat_id == chat_id)
        return list(self.session.exec(statement).all())

    def get_most_recent(self) -> MessageLog | None:
        """Get the most recent log entry across all chats."""
        return self.session.exec(
            select(MessageLog).order_by(MessageLog.created_at.desc()).limit(1)
        ).first()

    def get_most_recent_by_direction(
        self, direction: MessageDirection
    ) -> MessageLog | None:
        """Get the most recent log entry for a specific direction."""
        return self.session.exec(
            select(MessageLog)
            .where(MessageLog.direction == direction)
            .order_by(MessageLog.created_at.desc())
            .limit(1)
        ).first()

    def get_previous_sender_id(self, chat_id: int) -> int | None:
        """Get sender id from the latest known message in the chat."""
        log_entry = self.session.exec(
            select(MessageLog)
            .where(MessageLog.chat_id == chat_id)
            .order_by(MessageLog.created_at.desc())
            .limit(1)
        ).first()
        return log_entry.sender_id if log_entry else None

    def get_last_n_messages(self, chat_id: int, n: int = 12) -> list[MessageLog]:
        """Get last N messages for context."""
        return list(
            self.session.exec(
                select(MessageLog)
                .where(MessageLog.chat_id == chat_id)
                .order_by(MessageLog.created_at.desc())
                .limit(n)
            ).all()
        )


class PendingActionRepo:
    """Repository for pending actions."""

    def __init__(self, session: Session | AsyncSession):
        self.session = session

    def create(
        self,
        action_type: str,
        chat_id: int,
        text: str,
        reply_to_message_id: int | None = None,
    ) -> PendingAction:
        """Create a new pending action."""
        action = PendingAction(
            action_type=action_type,
            chat_id=chat_id,
            text=text,
            reply_to_message_id=reply_to_message_id,
        )
        self.session.add(action)
        self.session.commit()
        self.session.refresh(action)
        logger.info(f"Created pending action {action.id} for chat {chat_id}")
        return action

    def get_by_id(self, action_id: int) -> PendingAction | None:
        """Get pending action by ID."""
        return self.session.get(PendingAction, action_id)

    def get_pending(self) -> list[PendingAction]:
        """Get all pending actions."""
        return list(
            self.session.exec(
                select(PendingAction).where(PendingAction.status == ActionStatus.PENDING)
            ).all()
        )

    def approve(self, action_id: int) -> PendingAction | None:
        """Approve a pending action."""
        action = self.get_by_id(action_id)
        if action and action.status == ActionStatus.PENDING:
            action.status = ActionStatus.APPROVED
            action.decided_at = datetime.utcnow()
            self.session.commit()
            self.session.refresh(action)
            logger.info(f"Approved action {action_id}")
            return action
        return None

    def reject(self, action_id: int) -> PendingAction | None:
        """Reject a pending action."""
        action = self.get_by_id(action_id)
        if action and action.status == ActionStatus.PENDING:
            action.status = ActionStatus.REJECTED
            action.decided_at = datetime.utcnow()
            self.session.commit()
            self.session.refresh(action)
            logger.info(f"Rejected action {action_id}")
            return action
        return None

    def mark_executed(self, action_id: int, executed_message_id: int) -> PendingAction | None:
        """Mark action as executed."""
        action = self.get_by_id(action_id)
        if action:
            action.status = ActionStatus.EXECUTED
            action.executed_message_id = executed_message_id
            action.decided_at = datetime.utcnow()
            self.session.commit()
            self.session.refresh(action)
            logger.info(f"Marked action {action_id} as executed")
            return action
        return None

    def get_recent(self, limit: int = 10) -> list[PendingAction]:
        """Get recent actions."""
        return list(
            self.session.exec(
                select(PendingAction).order_by(PendingAction.created_at.desc()).limit(limit)
            ).all()
        )


class GlobalStateRepo:
    """Repository for global state."""

    def __init__(self, session: Session | AsyncSession):
        self.session = session

    def get(self, key: str) -> str | None:
        """Get value by key."""
        state = self.session.get(GlobalState, key)
        return state.value if state else None

    def set(self, key: str, value: str) -> GlobalState:
        """Set value for key."""
        state = self.session.get(GlobalState, key)
        if state is None:
            state = GlobalState(key=key, value=value)
            self.session.add(state)
        else:
            state.value = value
            state.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(state)
        return state

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get boolean value."""
        value = self.get(key)
        if value is None:
            return default
        return value.lower() in ("true", "1", "yes", "on")

    def set_bool(self, key: str, value: bool) -> GlobalState:
        """Set boolean value."""
        return self.set(key, "true" if value else "false")


class MonitoredChannelRepo:
    """Repository for monitored channels."""

    def __init__(self, session: Session | AsyncSession):
        self.session = session

    def get_all(self) -> list[MonitoredChannel]:
        """Get all monitored channels."""
        return self.session.exec(select(MonitoredChannel).where(MonitoredChannel.enabled == True)).all()

    def get_by_id(self, channel_id: int) -> MonitoredChannel | None:
        """Get channel by ID."""
        return self.session.exec(select(MonitoredChannel).where(MonitoredChannel.channel_id == channel_id)).first()

    def add(
        self,
        channel_id: int,
        channel_title: str | None = None,
        auto_outreach: bool = False,
        keywords: list[str] | None = None,
    ) -> MonitoredChannel:
        """Add or update monitored channel."""
        existing = self.get_by_id(channel_id)
        if existing:
            existing.channel_title = channel_title
            existing.auto_outreach = auto_outreach
            existing.keywords = ",".join(keywords) if keywords else None
            existing.updated_at = datetime.utcnow()
            self.session.commit()
            self.session.refresh(existing)
            logger.info(f"Updated monitored channel {channel_id}")
            return existing
        else:
            channel = MonitoredChannel(
                channel_id=channel_id,
                channel_title=channel_title,
                auto_outreach=auto_outreach,
                keywords=",".join(keywords) if keywords else None,
            )
            self.session.add(channel)
            self.session.commit()
            self.session.refresh(channel)
            logger.info(f"Added monitored channel {channel_id}")
            return channel

    def remove(self, channel_id: int) -> bool:
        """Remove monitored channel by ID. Returns True if removed."""
        channel = self.get_by_id(channel_id)
        if channel:
            self.session.delete(channel)
            self.session.commit()
            logger.info(f"Removed monitored channel {channel_id}")
            return True
        logger.warning(f"Channel {channel_id} not found")
        return False

    def set_enabled(self, channel_id: int, enabled: bool) -> MonitoredChannel | None:
        """Enable or disable a channel."""
        channel = self.get_by_id(channel_id)
        if channel:
            channel.enabled = enabled
            channel.updated_at = datetime.utcnow()
            self.session.commit()
            self.session.refresh(channel)
            return channel
        return None
