"""
Cooldown management for rate limiting.
"""

from datetime import datetime, timedelta

from tg_agent.logging import get_logger

logger = get_logger(__name__)


class CooldownManager:
    """
    Manages per-chat cooldowns to prevent spam.
    """

    def __init__(self, cooldown_seconds: int = 120):
        """
        Initialize cooldown manager.

        Args:
            cooldown_seconds: Minimum seconds between agent replies per chat.
        """
        self.cooldown_seconds = cooldown_seconds
        self._last_reply: dict[int, datetime] = {}

    def can_reply(self, chat_id: int, last_reply_at: datetime | None = None) -> bool:
        """
        Check if agent can reply to this chat.

        Args:
            chat_id: Target chat ID.
            last_reply_at: Last reply timestamp from DB (optional).

        Returns:
            True if reply is allowed.
        """
        # Use DB timestamp if available
        if last_reply_at is not None:
            cooldown_end = last_reply_at + timedelta(seconds=self.cooldown_seconds)
            if datetime.utcnow() < cooldown_end:
                logger.debug(f"Chat {chat_id} in cooldown until {cooldown_end}")
                return False

        # Also check in-memory cache
        if chat_id in self._last_reply:
            cooldown_end = self._last_reply[chat_id] + timedelta(
                seconds=self.cooldown_seconds
            )
            if datetime.utcnow() < cooldown_end:
                logger.debug(f"Chat {chat_id} in cooldown (memory) until {cooldown_end}")
                return False

        return True

    def record_reply(self, chat_id: int) -> None:
        """
        Record that agent replied to a chat.

        Args:
            chat_id: Chat that received a reply.
        """
        self._last_reply[chat_id] = datetime.utcnow()
        logger.debug(f"Recorded reply for chat {chat_id}")

    def get_cooldown_end(self, chat_id: int) -> datetime | None:
        """
        Get when cooldown ends for a chat.

        Args:
            chat_id: Chat ID.

        Returns:
            Datetime when cooldown ends, or None if not in cooldown.
        """
        if chat_id not in self._last_reply:
            return None

        cooldown_end = self._last_reply[chat_id] + timedelta(
            seconds=self.cooldown_seconds
        )
        now = datetime.utcnow()

        if now < cooldown_end:
            return cooldown_end
        return None

    def get_remaining_seconds(self, chat_id: int) -> int:
        """
        Get remaining cooldown seconds for a chat.

        Args:
            chat_id: Chat ID.

        Returns:
            Remaining seconds, or 0 if not in cooldown.
        """
        cooldown_end = self.get_cooldown_end(chat_id)
        if cooldown_end is None:
            return 0

        remaining = (cooldown_end - datetime.utcnow()).total_seconds()
        return max(0, int(remaining))

    def clear(self, chat_id: int) -> None:
        """
        Clear cooldown for a specific chat.

        Args:
            chat_id: Chat to clear.
        """
        if chat_id in self._last_reply:
            del self._last_reply[chat_id]
            logger.debug(f"Cleared cooldown for chat {chat_id}")

    def clear_all(self) -> None:
        """Clear all cooldowns."""
        self._last_reply.clear()
        logger.debug("Cleared all cooldowns")
