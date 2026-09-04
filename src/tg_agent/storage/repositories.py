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
    OutreachContact,
    OutreachStatus,
    PendingAction,
)

logger = get_logger(__name__)


class ChatSettingsRepo:
    """Repository for chat settings."""

    def __init__(self, session: Session | AsyncSession):
        self.session = session

    def get_by_chat_id(self, chat_id: int) -> ChatSettings | None:
        statement = select(ChatSettings).where(ChatSettings.chat_id == chat_id)
        return self.session.exec(statement).first()

    def get_or_create(
        self,
        chat_id: int,
        default_mode: ChatMode = ChatMode.OFF,
        chat_title: str | None = None,
    ) -> ChatSettings:
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
        settings = self.get_or_create(chat_id)
        settings.mode = mode
        settings.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(settings)
        logger.info(f"Updated chat {chat_id} mode to {mode.value}")
        return settings

    def set_trusted(self, chat_id: int, trusted: bool = True) -> ChatSettings:
        settings = self.get_or_create(chat_id)
        settings.is_trusted = trusted
        settings.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(settings)
        logger.info(f"Set chat {chat_id} trusted={trusted}")
        return settings

    def update_last_message(self, chat_id: int, message_id: int) -> None:
        settings = self.get_or_create(chat_id)
        settings.last_incoming_message_id = message_id
        settings.updated_at = datetime.utcnow()
        self.session.commit()

    def update_last_agent_reply(
        self,
        chat_id: int,
        replied_at: datetime | None = None,
    ) -> None:
        settings = self.get_or_create(chat_id)
        settings.last_agent_reply_at = replied_at or datetime.utcnow()
        settings.updated_at = datetime.utcnow()
        self.session.commit()

    def set_paused_until(self, chat_id: int, until: datetime | None) -> None:
        settings = self.get_or_create(chat_id)
        settings.paused_until = until
        settings.updated_at = datetime.utcnow()
        self.session.commit()

    def get_all(self) -> list[ChatSettings]:
        return list(self.session.exec(select(ChatSettings)).all())

    def get_by_mode(self, mode: ChatMode) -> list[ChatSettings]:
        return list(
            self.session.exec(
                select(ChatSettings).where(ChatSettings.mode == mode)
            ).all()
        )


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
        statement = select(MessageLog).where(
            MessageLog.chat_id == chat_id,
            MessageLog.message_id == message_id,
        )
        if direction is not None:
            statement = statement.where(MessageLog.direction == direction)
        return self.session.exec(statement.limit(1)).first() is not None

    def get_recent(self, chat_id: int, limit: int = 10) -> list[MessageLog]:
        statement = select(MessageLog).order_by(MessageLog.created_at.desc()).limit(limit)
        if chat_id:
            statement = statement.where(MessageLog.chat_id == chat_id)
        return list(self.session.exec(statement).all())

    def get_most_recent(self) -> MessageLog | None:
        return self.session.exec(
            select(MessageLog).order_by(MessageLog.created_at.desc()).limit(1)
        ).first()

    def get_most_recent_by_direction(
        self,
        direction: MessageDirection,
    ) -> MessageLog | None:
        return self.session.exec(
            select(MessageLog)
            .where(MessageLog.direction == direction)
            .order_by(MessageLog.created_at.desc())
            .limit(1)
        ).first()

    def get_previous_sender_id(self, chat_id: int) -> int | None:
        log_entry = self.session.exec(
            select(MessageLog)
            .where(MessageLog.chat_id == chat_id)
            .order_by(MessageLog.created_at.desc())
            .limit(1)
        ).first()
        return log_entry.sender_id if log_entry else None

    def get_last_n_messages(self, chat_id: int, n: int = 12) -> list[MessageLog]:
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
        return self.session.get(PendingAction, action_id)

    def get_pending(self) -> list[PendingAction]:
        return list(
            self.session.exec(
                select(PendingAction).where(PendingAction.status == ActionStatus.PENDING)
            ).all()
        )

    def claim_for_execution(self, action_id: int) -> PendingAction | None:
        """Atomically-ish claim a pending action before doing the side effect.

        SQLite serializes the commit. A second approval handler will observe the
        EXECUTING state and refuse to send the same action twice.
        """
        action = self.get_by_id(action_id)
        if action is None or action.status != ActionStatus.PENDING:
            return None
        action.status = ActionStatus.EXECUTING
        self.session.commit()
        self.session.refresh(action)
        logger.info(f"Claimed action {action_id} for execution")
        return action

    def reset_pending(self, action_id: int) -> PendingAction | None:
        """Return a failed execution claim to PENDING so the owner may retry."""
        action = self.get_by_id(action_id)
        if action and action.status == ActionStatus.EXECUTING:
            action.status = ActionStatus.PENDING
            self.session.commit()
            self.session.refresh(action)
            logger.warning(f"Reset action {action_id} to pending after send failure")
            return action
        return None

    def approve(self, action_id: int) -> PendingAction | None:
        """Legacy explicit approval transition."""
        action = self.get_by_id(action_id)
        if action and action.status in (ActionStatus.PENDING, ActionStatus.EXECUTING):
            action.status = ActionStatus.APPROVED
            action.decided_at = datetime.utcnow()
            self.session.commit()
            self.session.refresh(action)
            logger.info(f"Approved action {action_id}")
            return action
        return None

    def reject(self, action_id: int) -> PendingAction | None:
        action = self.get_by_id(action_id)
        if action and action.status == ActionStatus.PENDING:
            action.status = ActionStatus.REJECTED
            action.decided_at = datetime.utcnow()
            self.session.commit()
            self.session.refresh(action)
            logger.info(f"Rejected action {action_id}")
            return action
        return None

    def mark_executed(
        self,
        action_id: int,
        executed_message_id: int,
    ) -> PendingAction | None:
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
        state = self.session.get(GlobalState, key)
        return state.value if state else None

    def set(self, key: str, value: str) -> GlobalState:
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
        value = self.get(key)
        if value is None:
            return default
        return value.lower() in ("true", "1", "yes", "on")

    def set_bool(self, key: str, value: bool) -> GlobalState:
        return self.set(key, "true" if value else "false")


class MonitoredChannelRepo:
    """Repository for monitored channels."""

    def __init__(self, session: Session | AsyncSession):
        self.session = session

    def get_all(self) -> list[MonitoredChannel]:
        return list(
            self.session.exec(
                select(MonitoredChannel).where(MonitoredChannel.enabled == True)  # noqa: E712
            ).all()
        )

    def get_by_id(self, channel_id: int) -> MonitoredChannel | None:
        return self.session.exec(
            select(MonitoredChannel).where(MonitoredChannel.channel_id == channel_id)
        ).first()

    def add(
        self,
        channel_id: int,
        channel_title: str | None = None,
        auto_outreach: bool = False,
        keywords: list[str] | None = None,
    ) -> MonitoredChannel:
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
        channel = self.get_by_id(channel_id)
        if channel:
            self.session.delete(channel)
            self.session.commit()
            logger.info(f"Removed monitored channel {channel_id}")
            return True
        logger.warning(f"Channel {channel_id} not found")
        return False

    def set_enabled(
        self,
        channel_id: int,
        enabled: bool,
    ) -> MonitoredChannel | None:
        channel = self.get_by_id(channel_id)
        if channel:
            channel.enabled = enabled
            channel.updated_at = datetime.utcnow()
            self.session.commit()
            self.session.refresh(channel)
            return channel
        return None


class OutreachContactRepo:
    """Durable deduplication, retry state, and per-channel outreach audit."""

    def __init__(self, session: Session | AsyncSession):
        self.session = session

    def get_by_username(self, username: str) -> OutreachContact | None:
        normalized = username.lower().lstrip("@")
        return self.session.exec(
            select(OutreachContact).where(OutreachContact.username == normalized)
        ).first()

    def claim(self, username: str, channel_id: int) -> OutreachContact | None:
        """Claim a username for sending.

        SENT and PENDING contacts are deduplicated. FAILED contacts may be retried.
        """
        normalized = username.lower().lstrip("@")
        existing = self.get_by_username(normalized)
        if existing:
            if existing.status in (OutreachStatus.SENT, OutreachStatus.PENDING):
                return None
            existing.status = OutreachStatus.PENDING
            existing.channel_id = channel_id
            existing.last_error = None
            existing.updated_at = datetime.utcnow()
            self.session.commit()
            self.session.refresh(existing)
            return existing

        contact = OutreachContact(
            username=normalized,
            channel_id=channel_id,
            status=OutreachStatus.PENDING,
        )
        self.session.add(contact)
        self.session.commit()
        self.session.refresh(contact)
        return contact

    def mark_sent(
        self,
        username: str,
        sent_message_id: int,
    ) -> OutreachContact | None:
        contact = self.get_by_username(username)
        if contact is None:
            return None
        now = datetime.utcnow()
        contact.status = OutreachStatus.SENT
        contact.sent_message_id = sent_message_id
        contact.sent_at = now
        contact.updated_at = now
        contact.last_error = None
        self.session.commit()
        self.session.refresh(contact)
        return contact

    def mark_failed(self, username: str, error: str) -> OutreachContact | None:
        contact = self.get_by_username(username)
        if contact is None:
            return None
        contact.status = OutreachStatus.FAILED
        contact.last_error = error[:1000]
        contact.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(contact)
        return contact

    def count_sent_since(self, channel_id: int, since: datetime) -> int:
        return len(
            self.session.exec(
                select(OutreachContact).where(
                    OutreachContact.channel_id == channel_id,
                    OutreachContact.status == OutreachStatus.SENT,
                    OutreachContact.sent_at >= since,
                )
            ).all()
        )
