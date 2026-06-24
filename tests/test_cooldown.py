"""
Tests for cooldown module.
"""

from datetime import datetime, timedelta

import pytest

from tg_agent.policy.cooldown import CooldownManager


class TestCooldownManager:
    """Tests for CooldownManager class."""

    @pytest.fixture
    def cooldown_manager(self):
        return CooldownManager(cooldown_seconds=60)

    def test_can_reply_initial(self, cooldown_manager):
        """Should allow reply when no previous reply exists."""
        assert cooldown_manager.can_reply(chat_id=1) is True

    def test_cannot_reply_during_cooldown(self, cooldown_manager):
        """Should block reply during cooldown period."""
        chat_id = 1
        cooldown_manager.record_reply(chat_id)

        # Should be in cooldown
        assert cooldown_manager.can_reply(chat_id) is False

    def test_can_reply_after_cooldown(self, cooldown_manager):
        """Should allow reply after cooldown expires."""
        chat_id = 1

        # Record reply with old timestamp
        old_time = datetime.utcnow() - timedelta(seconds=120)
        cooldown_manager._last_reply[chat_id] = old_time

        # Should be out of cooldown
        assert cooldown_manager.can_reply(chat_id) is True

    def test_record_reply(self, cooldown_manager):
        """Should record reply timestamp."""
        chat_id = 1
        cooldown_manager.record_reply(chat_id)

        assert chat_id in cooldown_manager._last_reply
        assert isinstance(cooldown_manager._last_reply[chat_id], datetime)

    def test_get_cooldown_end(self, cooldown_manager):
        """Should return correct cooldown end time."""
        chat_id = 1
        cooldown_manager.record_reply(chat_id)

        cooldown_end = cooldown_manager.get_cooldown_end(chat_id)
        assert cooldown_end is not None

        # Should be approximately 60 seconds from now
        expected_end = datetime.utcnow() + timedelta(seconds=60)
        diff = abs((cooldown_end - expected_end).total_seconds())
        assert diff < 2  # Allow 2 second tolerance

    def test_get_cooldown_end_no_cooldown(self, cooldown_manager):
        """Should return None when not in cooldown."""
        assert cooldown_manager.get_cooldown_end(chat_id=999) is None

    def test_get_remaining_seconds(self, cooldown_manager):
        """Should return remaining cooldown seconds."""
        chat_id = 1
        cooldown_manager.record_reply(chat_id)

        remaining = cooldown_manager.get_remaining_seconds(chat_id)
        assert 55 <= remaining <= 60  # Allow some tolerance

    def test_get_remaining_seconds_expired(self, cooldown_manager):
        """Should return 0 when cooldown expired."""
        chat_id = 1
        old_time = datetime.utcnow() - timedelta(seconds=120)
        cooldown_manager._last_reply[chat_id] = old_time

        remaining = cooldown_manager.get_remaining_seconds(chat_id)
        assert remaining == 0

    def test_clear(self, cooldown_manager):
        """Should clear cooldown for specific chat."""
        chat_id = 1
        cooldown_manager.record_reply(chat_id)
        assert chat_id in cooldown_manager._last_reply

        cooldown_manager.clear(chat_id)
        assert chat_id not in cooldown_manager._last_reply

    def test_clear_all(self, cooldown_manager):
        """Should clear all cooldowns."""
        cooldown_manager.record_reply(1)
        cooldown_manager.record_reply(2)
        cooldown_manager.record_reply(3)

        cooldown_manager.clear_all()
        assert len(cooldown_manager._last_reply) == 0

    def test_can_reply_with_db_timestamp(self, cooldown_manager):
        """Should respect DB timestamp when provided."""
        chat_id = 1
        old_timestamp = datetime.utcnow() - timedelta(seconds=120)

        # Should allow reply with old timestamp
        assert cooldown_manager.can_reply(chat_id, last_reply_at=old_timestamp) is True

        # Should block with recent timestamp
        recent_timestamp = datetime.utcnow() - timedelta(seconds=30)
        assert cooldown_manager.can_reply(chat_id, last_reply_at=recent_timestamp) is False

    def test_multiple_chats_independent(self, cooldown_manager):
        """Should handle multiple chats independently."""
        cooldown_manager.record_reply(1)

        # Chat 1 in cooldown, chat 2 should be free
        assert cooldown_manager.can_reply(1) is False
        assert cooldown_manager.can_reply(2) is True
