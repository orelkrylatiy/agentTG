"""Tests for HITL (Human-in-the-Loop) module."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_agent.storage.models import ActionStatus, PendingAction


class TestPendingActionModel:
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
    def test_status_values(self):
        assert ActionStatus.PENDING.value == "pending"
        assert ActionStatus.EXECUTING.value == "executing"
        assert ActionStatus.APPROVED.value == "approved"
        assert ActionStatus.REJECTED.value == "rejected"
        assert ActionStatus.EXECUTED.value == "executed"
        assert ActionStatus.EXPIRED.value == "expired"


class TestHITLManager:
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
    def repos(self, monkeypatch):
        pending_repo = MagicMock()
        message_log_repo = MagicMock()
        monkeypatch.setattr(
            "tg_agent.control_bot.hitl.PendingActionRepo",
            lambda _session: pending_repo,
        )
        monkeypatch.setattr(
            "tg_agent.control_bot.hitl.MessageLogRepo",
            lambda _session: message_log_repo,
        )
        return pending_repo, message_log_repo

    @pytest.fixture
    def hitl_manager(self, mock_settings, mock_db, mock_control_bot, mock_sender):
        from tg_agent.control_bot.hitl import HITLManager

        return HITLManager(
            settings=mock_settings,
            db=mock_db,
            control_bot=mock_control_bot,
            sender=mock_sender,
        )

    @staticmethod
    def action(action_type: str = "reply", status: ActionStatus = ActionStatus.PENDING):
        action = MagicMock(spec=PendingAction)
        action.id = 1
        action.status = status
        action.action_type = action_type
        action.chat_id = 123
        action.text = "Test reply"
        action.reply_to_message_id = 456 if action_type == "reply" else None
        return action

    @pytest.mark.asyncio
    async def test_approve_reply_action(self, hitl_manager, repos):
        pending_repo, message_log_repo = repos
        action = self.action("reply")
        pending_repo.get_by_id.return_value = action
        pending_repo.claim_for_execution.return_value = action

        success, _ = await hitl_manager._process_approval(1)

        assert success is True
        pending_repo.claim_for_execution.assert_called_once_with(1)
        hitl_manager.sender.send_reply.assert_awaited_once()
        pending_repo.mark_executed.assert_called_once_with(1, 999)
        message_log_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_approve_send_message_action(self, hitl_manager, repos):
        pending_repo, _ = repos
        action = self.action("send_message")
        pending_repo.get_by_id.return_value = action
        pending_repo.claim_for_execution.return_value = action

        success, _ = await hitl_manager._process_approval(1)

        assert success is True
        hitl_manager.sender.send_message.assert_awaited_once()
        pending_repo.mark_executed.assert_called_once_with(1, 999)

    @pytest.mark.asyncio
    async def test_send_failure_returns_action_to_pending(
        self,
        hitl_manager,
        repos,
    ):
        pending_repo, _ = repos
        action = self.action("reply")
        pending_repo.get_by_id.return_value = action
        pending_repo.claim_for_execution.return_value = action
        hitl_manager.sender.send_reply.return_value = None

        success, message = await hitl_manager._process_approval(1)

        assert success is False
        assert "retried" in message
        pending_repo.reset_pending.assert_called_once_with(1)
        pending_repo.mark_executed.assert_not_called()

    @pytest.mark.asyncio
    async def test_approve_action_not_found(self, hitl_manager, repos):
        pending_repo, _ = repos
        pending_repo.get_by_id.return_value = None

        success, message = await hitl_manager._process_approval(999)

        assert success is False
        assert "not found" in message

    @pytest.mark.asyncio
    async def test_approve_already_processed(self, hitl_manager, repos):
        pending_repo, _ = repos
        pending_repo.get_by_id.return_value = self.action(
            "reply",
            ActionStatus.EXECUTED,
        )

        success, message = await hitl_manager._process_approval(1)

        assert success is False
        assert "already executed" in message
        pending_repo.claim_for_execution.assert_not_called()

    @pytest.mark.asyncio
    async def test_reject_action(self, hitl_manager, repos):
        pending_repo, _ = repos
        pending_repo.get_by_id.return_value = self.action("reply")

        success = await hitl_manager._process_rejection(1)

        assert success is True
        pending_repo.reject.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_reject_already_processed(self, hitl_manager, repos):
        pending_repo, _ = repos
        pending_repo.get_by_id.return_value = self.action(
            "reply",
            ActionStatus.EXECUTED,
        )

        success = await hitl_manager._process_rejection(1)
        assert success is False


class TestApprovalKeyboard:
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
