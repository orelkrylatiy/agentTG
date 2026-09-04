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
    """Manage owner approval and safe execution of pending actions."""

    def __init__(
        self,
        settings: Settings,
        db: Database,
        control_bot: ControlBot,
        sender: MessageSender,
    ):
        self.settings = settings
        self.db = db
        self.control_bot = control_bot
        self.sender = sender
        self.owner_id = settings.owner_telegram_id

    def register_handlers(self, dp: Dispatcher) -> None:
        dp.callback_query.register(
            self._on_approve,
            lambda c: c.data.startswith("approve:"),
        )
        dp.callback_query.register(
            self._on_reject,
            lambda c: c.data.startswith("reject:"),
        )
        logger.info("HITL handlers registered")

    async def _on_approve(self, callback: CallbackQuery) -> None:
        if not self.control_bot.is_owner(callback.from_user.id):
            await callback.answer("⛔ Access denied", show_alert=True)
            return

        try:
            action_id = int(callback.data.split(":")[1])
        except (IndexError, ValueError):
            await callback.answer("❌ Invalid action ID", show_alert=True)
            return

        success, message = await self._process_approval(action_id)

        if success:
            await callback.message.edit_text(
                text=callback.message.text + "\n\n✅ <b>APPROVED</b>",
                parse_mode="HTML",
            )
            await callback.answer("✅ Approved and sent", show_alert=False)
        else:
            await callback.answer(f"❌ {message}", show_alert=True)

    async def _on_reject(self, callback: CallbackQuery) -> None:
        if not self.control_bot.is_owner(callback.from_user.id):
            await callback.answer("⛔ Access denied", show_alert=True)
            return

        try:
            action_id = int(callback.data.split(":")[1])
        except (IndexError, ValueError):
            await callback.answer("❌ Invalid action ID", show_alert=True)
            return

        success = await self._process_rejection(action_id)
        if success:
            await callback.message.edit_text(
                text=callback.message.text + "\n\n❌ <b>REJECTED</b>",
                parse_mode="HTML",
            )
            await callback.answer("❌ Rejected", show_alert=False)
        else:
            await callback.answer("❌ Failed to reject", show_alert=True)

    async def _process_approval(self, action_id: int) -> tuple[bool, str]:
        """Claim, execute, and persist an approved action without double-send risk."""
        # Claim before the network side effect. This prevents two rapid callback
        # deliveries from sending the same message twice.
        with self.db.get_sync_session() as session:
            pending_repo = PendingActionRepo(session)
            action = pending_repo.get_by_id(action_id)
            if action is None:
                return False, "Action not found"
            if action.status != ActionStatus.PENDING:
                return False, f"Action already {action.status.value}"

            claimed = pending_repo.claim_for_execution(action_id)
            if claimed is None:
                return False, "Action is already being processed"

            action_type = claimed.action_type
            chat_id = claimed.chat_id
            text = claimed.text
            reply_to_message_id = claimed.reply_to_message_id

        # Never keep a SQLite session/transaction open while waiting on Telegram.
        if action_type == "reply":
            sent_message = await self.sender.send_reply(
                chat_id=chat_id,
                text=text,
                reply_to_message_id=reply_to_message_id,
                simulate_typing=True,
            )
        elif action_type == "send_message":
            sent_message = await self.sender.send_message(
                chat_id=chat_id,
                text=text,
                simulate_typing=True,
            )
        else:
            with self.db.get_sync_session() as session:
                PendingActionRepo(session).reset_pending(action_id)
            return False, f"Unknown action type: {action_type}"

        if sent_message is None:
            # A transport failure must be retryable. Returning the action to
            # PENDING is safer than leaving it stuck in APPROVED/EXECUTING.
            with self.db.get_sync_session() as session:
                PendingActionRepo(session).reset_pending(action_id)
            return False, "Failed to send message; action can be retried"

        with self.db.get_sync_session() as session:
            PendingActionRepo(session).mark_executed(action_id, sent_message.id)
            MessageLogRepo(session).create(
                chat_id=chat_id,
                message_id=sent_message.id,
                sender_id=self.owner_id,
                direction=MessageDirection.AGENT_SENT,
                text=text,
            )

        logger.info(f"Action {action_id} approved and executed")
        return True, "Message sent"

    async def _process_rejection(self, action_id: int) -> bool:
        with self.db.get_sync_session() as session:
            pending_repo = PendingActionRepo(session)
            action = pending_repo.get_by_id(action_id)
            if action is None or action.status != ActionStatus.PENDING:
                return False
            pending_repo.reject(action_id)
            logger.info(f"Action {action_id} rejected")
            return True
