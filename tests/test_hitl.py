"""
Tests for HITL (Human-in-the-Loop) module.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_agent.storage.models import ActionStatus, PendingAction


class TestPendingActionModel:
    """Tests for PendingAction model."""

    def test_create_pending_action(self):
        action = PendingAction(
            action_type="reply",
            chat_id=123,
            text="Test reply",
            reply_to_message_id=456,
        )
        assert action.action_type == "reply"
        assert action.chat_id == 123
        assert action.text == "Test reply"
        assert action.status == ActionStatus.PENDING
        assert action.executed_message_id is None


class TestActionStatus:
    """Tests for ActionStatus enum."""

    def test_status_values(self):
        assert ActionStatus.PENDING.value == "pending"
        assert ActionStatus.APPROVED.value == "approved"
        assert ActionStatus.REJECTED.value == "rejected"
        assert ActionStatus.EXECUTED.value == "executed"
        assert ActionStatus.EXPIRED.value == "expired"


class TestHITLManager:
    """Tests for HITLManager class."""

    @pytest.fixture
    def mock_settings(self):
        class MockSettings:
            owner_telegram_id = 123456
        return MockSettings()

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        session = MagicMock()
        db.get_sync_session.return_value.__enter__ = MagicMock(return_value=session)
        db.get_sync_session.return_value.__exit__ = MagicMock(return_value=False)
        return db

    @pytest.fixture
    def mock_control_bot(self):
        bot = MagicMock()
        bot.is_owner = MagicMock(return_value=True)
        return bot

    @pytest.fixture
    def mock_sender(self):
        sender = AsyncMock()
        sender.send_reply = AsyncMock(return_value=MagicMock(id=999))
        sender.send_message = AsyncMock(return_value=MagicMock(id=999))
        return sender

    @pytest.fixture
    def hitl_manager(self, mock_settings, mock_db, mock_control_bot, mock_sender):
        from tg_agent.control_bot.hitl import HITLManager
        return HITLManager(
            settings=mock_settings,
            db=mock_db,
            control_bot=mock_control_bot,
            sender=mock_sender,
        )

    @pytest.mark.asyncio
    async def test_approve_reply_action(self, hitl_manager, mock_db):
        """Test approving a reply action."""
        # Mock pending action
        mock_action = MagicMock(spec=PendingAction)
        mock_action.id = 1
        mock_action.status = ActionStatus.PENDING
        mock_action.action_type = "reply"
        mock_action.chat_id = 123
        mock_action.text = "Test reply"
        mock_action.reply_to_message_id = 456

        mock_repo = MagicMock()
        mock_repo.get_by_id.return_value = mock_action
        mock_db.get_sync_session.return_value.__enter__.return_value = mock_repo

        success, message = await hitl_manager._process_approval(1)

        assert success is True
        assert mock_repo.approve.called
        assert hitl_manager.sender.send_reply.called

    @pytest.mark.asyncio
    async def test_approve_send_message_action(self, hitl_manager, mock_db):
        """Test approving a send_message action."""
        mock_action = MagicMock(spec=PendingAction)
        mock_action.id = 2
        mock_action.status = ActionStatus.PENDING
        mock_action.action_type = "send_message"
        mock_action.chat_id = 123
        mock_action.text = "Test message"
        mock_action.reply_to_message_id = None

        mock_repo = MagicMock()
        mock_repo.get_by_id.return_value = mock_action
        mock_db.get_sync_session.return_value.__enter__.return_value = mock_repo

        success, message = await hitl_manager._process_approval(2)

        assert success is True
        assert hitl_manager.sender.send_message.called

    @pytest.mark.asyncio
    async def test_approve_action_not_found(self, hitl_manager, mock_db):
        """Test approving non-existent action."""
        mock_repo = MagicMock()
        mock_repo.get_by_id.return_value = None
        mock_db.get_sync_session.return_value.__enter__.return_value = mock_repo

        success, message = await hitl_manager._process_approval(999)

        assert success is False
        assert "not found" in message

    @pytest.mark.asyncio
    async def test_approve_already_processed(self, hitl_manager, mock_db):
        """Test approving already processed action."""
        mock_action = MagicMock(spec=PendingAction)
        mock_action.id = 1
        mock_action.status = ActionStatus.EXECUTED

        mock_repo = MagicMock()
        mock_repo.get_by_id.return_value = mock_action
        mock_db.get_sync_session.return_value.__enter__.return_value = mock_repo

        success, message = await hitl_manager._process_approval(1)

        assert success is False

    @pytest.mark.asyncio
    async def test_reject_action(self, hitl_manager, mock_db):
        """Test rejecting an action."""
        mock_action = MagicMock(spec=PendingAction)
        mock_action.id = 1
        mock_action.status = ActionStatus.PENDING

        mock_repo = MagicMock()
        mock_repo.get_by_id.return_value = mock_action
        mock_db.get_sync_session.return_value.__enter__.return_value = mock_repo

        success = await hitl_manager._process_rejection(1)

        assert success is True
        assert mock_repo.reject.called

    @pytest.mark.asyncio
    async def test_reject_already_processed(self, hitl_manager, mock_db):
        """Test rejecting already processed action."""
        mock_action = MagicMock(spec=PendingAction)
        mock_action.id = 1
        mock_action.status = ActionStatus.EXECUTED

        mock_repo = MagicMock()
        mock_repo.get_by_id.return_value = mock_action
        mock_db.get_sync_session.return_value.__enter__.return_value = mock_repo

        success = await hitl_manager._process_rejection(1)

        assert success is False


class TestApprovalKeyboard:
    """Tests for approval inline keyboard."""

    def test_create_approval_keyboard(self):
        from tg_agent.control_bot.keyboards import create_approval_keyboard

        keyboard = create_approval_keyboard(action_id=42)

        assert len(keyboard.inline_keyboard) == 1
        assert len(keyboard.inline_keyboard[0]) == 2

        approve_btn = keyboard.inline_keyboard[0][0]
        reject_btn = keyboard.inline_keyboard[0][1]

        assert approve_btn.text == "✅ Approve"
        assert approve_btn.callback_data == "approve:42"
        assert reject_btn.text == "❌ Reject"
        assert reject_btn.callback_data == "reject:42"
