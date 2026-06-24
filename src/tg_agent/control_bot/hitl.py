"""
Human-in-the-loop (HITL) manager for draft approval.
"""

from typing import TYPE_CHECKING, Any

try:
    from aiogram import Dispatcher
    from aiogram.types import CallbackQuery
except ImportError:  # pragma: no cover
    Dispatcher = Any
    CallbackQuery = Any

from tg_agent.logging import get_logger
from tg_agent.storage.db import Database
from tg_agent.storage.models import ActionStatus, MessageDirection
from tg_agent.storage.repositories import MessageLogRepo, PendingActionRepo

if TYPE_CHECKING:
    from tg_agent.config import Settings
    from tg_agent.control_bot.bot import ControlBot
    from tg_agent.userbot.sender import MessageSender
else:
    Settings = Any
    ControlBot = Any
    MessageSender = Any

logger = get_logger(__name__)


class HITLManager:
    """
    Manages human-in-the-loop approval workflow.

    Handles approve/reject callbacks for pending actions.
    """

    def __init__(
        self,
        settings: Settings,
        db: Database,
        control_bot: ControlBot,
        sender: MessageSender,
    ):
        """
        Initialize HITL manager.

        Args:
            settings: Application settings.
            db: Database instance.
            control_bot: Control bot instance.
            sender: Message sender instance.
        """
        self.settings = settings
        self.db = db
        self.control_bot = control_bot
        self.sender = sender
        self.owner_id = settings.owner_telegram_id

    def register_handlers(self, dp: Dispatcher) -> None:
        """
        Register callback handlers.

        Args:
            dp: aiogram Dispatcher.
        """
        dp.callback_query.register(self._on_approve, lambda c: c.data.startswith("approve:"))
        dp.callback_query.register(self._on_reject, lambda c: c.data.startswith("reject:"))
        logger.info("HITL handlers registered")

    @staticmethod
    def _pending_repo(session):
        if all(hasattr(session, name) for name in ("get_by_id", "approve", "reject")):
            return session
        return PendingActionRepo(session)

    @staticmethod
    def _message_log_repo(session):
        if hasattr(session, "create"):
            return session
        return MessageLogRepo(session)

    async def _on_approve(self, callback: CallbackQuery) -> None:
        """
        Handle approve callback.

        Args:
            callback: Callback query.
        """
        # Verify owner
        if not self.control_bot.is_owner(callback.from_user.id):
            await callback.answer("⛔ Access denied", show_alert=True)
            return

        # Parse action ID
        try:
            action_id = int(callback.data.split(":")[1])
        except (IndexError, ValueError):
            await callback.answer("❌ Invalid action ID", show_alert=True)
            return

        # Process approval
        success, message = await self._process_approval(action_id)

        # Update the original message
        if success:
            await callback.message.edit_text(
                text=callback.message.text + "\n\n✅ <b>APPROVED</b>",
                parse_mode="HTML",
            )
            await callback.answer("✅ Approved and sent", show_alert=False)
        else:
            await callback.answer(f"❌ {message}", show_alert=True)

    async def _on_reject(self, callback: CallbackQuery) -> None:
        """
        Handle reject callback.

        Args:
            callback: Callback query.
        """
        # Verify owner
        if not self.control_bot.is_owner(callback.from_user.id):
            await callback.answer("⛔ Access denied", show_alert=True)
            return

        # Parse action ID
        try:
            action_id = int(callback.data.split(":")[1])
        except (IndexError, ValueError):
            await callback.answer("❌ Invalid action ID", show_alert=True)
            return

        # Process rejection
        success = await self._process_rejection(action_id)

        # Update the original message
        if success:
            await callback.message.edit_text(
                text=callback.message.text + "\n\n❌ <b>REJECTED</b>",
                parse_mode="HTML",
            )
            await callback.answer("❌ Rejected", show_alert=False)
        else:
            await callback.answer("❌ Failed to reject", show_alert=True)

    async def _process_approval(self, action_id: int) -> tuple[bool, str]:
        """
        Process action approval.

        Args:
            action_id: Pending action ID.

        Returns:
            Tuple of (success, message).
        """
        with self.db.get_sync_session() as session:
            pending_repo = self._pending_repo(session)
            message_log_repo = self._message_log_repo(session)

            # Get action
            action = pending_repo.get_by_id(action_id)
            if action is None:
                return False, "Action not found"

            if action.status != ActionStatus.PENDING:
                return False, f"Action already {action.status.value}"

            # Approve the action
            pending_repo.approve(action_id)

            # Execute the action
            if action.action_type == "reply":
                sent_message = await self.sender.send_reply(
                    chat_id=action.chat_id,
                    text=action.text,
                    reply_to_message_id=action.reply_to_message_id,
                    simulate_typing=True,
                )
            elif action.action_type == "send_message":
                sent_message = await self.sender.send_message(
                    chat_id=action.chat_id,
                    text=action.text,
                    simulate_typing=True,
                )
            else:
                return False, f"Unknown action type: {action.action_type}"

            if sent_message is None:
                return False, "Failed to send message"

            # Mark as executed
            pending_repo.mark_executed(action_id, sent_message.id)

            # Log the message
            message_log_repo.create(
                chat_id=action.chat_id,
                message_id=sent_message.id,
                sender_id=self.owner_id,
                direction=MessageDirection.AGENT_SENT,
                text=action.text,
            )

            logger.info(f"Action {action_id} approved and executed")
            return True, "Message sent"

    async def _process_rejection(self, action_id: int) -> bool:
        """
        Process action rejection.

        Args:
            action_id: Pending action ID.

        Returns:
            True if successful.
        """
        with self.db.get_sync_session() as session:
            pending_repo = self._pending_repo(session)

            action = pending_repo.get_by_id(action_id)
            if action is None:
                return False

            if action.status != ActionStatus.PENDING:
                return False

            pending_repo.reject(action_id)
            logger.info(f"Action {action_id} rejected")
            return True
