"""
Incoming message handlers for Telethon userbot.
"""


from telethon import TelegramClient, events
from telethon.tl.types import Message

from tg_agent.agent.llm import LLMClient
from tg_agent.agent.reply import ReplyGenerator
from tg_agent.config import Settings
from tg_agent.control_bot import ControlBot
from tg_agent.logging import get_logger
from tg_agent.policy.cooldown import CooldownManager
from tg_agent.policy.filters import MessageFilter
from tg_agent.policy.gate import PolicyGate
from tg_agent.storage.db import Database
from tg_agent.storage.models import ChatMode, MessageDirection
from tg_agent.storage.repositories import (
    ChatSettingsRepo,
    MessageLogRepo,
    PendingActionRepo,
)
from tg_agent.userbot.sender import MessageSender

logger = get_logger(__name__)


class IncomingMessageHandler:
    """
    Handles incoming messages for the userbot.
    """

    def __init__(
        self,
        settings: Settings,
        db: Database,
        client: TelegramClient,
        control_bot: ControlBot,
        llm_client: LLMClient,
    ):
        """
        Initialize message handler.

        Args:
            settings: Application settings.
            db: Database instance.
            client: Telethon client.
            control_bot: Control bot for notifications.
            llm_client: LLM client for reply generation.
        """
        self.settings = settings
        self.db = db
        self.client = client
        self.control_bot = control_bot
        self.llm_client = llm_client

        # Initialize components
        self.sender = MessageSender(client)
        self.reply_generator = ReplyGenerator(settings, llm_client)
        self.cooldown_manager = CooldownManager(settings.cooldown_seconds)
        self.message_filter = MessageFilter()
        self.policy_gate = PolicyGate(
            settings,
            self.cooldown_manager,
            self.message_filter,
        )

        self.owner_id = settings.owner_telegram_id

    def register_handlers(self) -> None:
        """Register event handlers with the client."""
        self.client.add_event_handler(
            self._on_new_message,
            events.NewMessage(incoming=True),
        )
        logger.info("Incoming message handler registered")

    async def _on_new_message(self, event: events.NewMessage) -> None:
        """
        Handle new incoming message.

        Args:
            event: New message event.
        """
        message = event.message
        chat_id = event.chat_id
        sender_id = event.sender_id if event.sender else None

        # Skip messages from self
        if message.out:
            return

        # Skip messages from bots
        if event.sender and event.sender.bot:
            logger.debug(f"Skipping bot message from {sender_id}")
            return

        logger.info(f"New message in chat {chat_id} from {sender_id}")

        chat_title = getattr(getattr(event, "chat", None), "title", None)
        with self.db.get_sync_session() as session:
            chat_settings_repo = ChatSettingsRepo(session)
            message_log_repo = MessageLogRepo(session)
            previous_sender_id = message_log_repo.get_previous_sender_id(chat_id)

            default_mode = ChatMode(self.settings.default_chat_mode)
            chat_settings = chat_settings_repo.get_or_create(
                chat_id=chat_id,
                default_mode=default_mode,
                chat_title=chat_title,
            )

            decision = self.policy_gate.evaluate(
                chat_settings=chat_settings,
                sender_id=sender_id or 0,
                message_text=message.text or "",
                last_message_sender_id=previous_sender_id,
            )

            message_log_repo.create(
                chat_id=chat_id,
                message_id=message.id,
                sender_id=sender_id,
                direction=MessageDirection.INCOMING,
                text=message.text,
            )
            chat_settings_repo.update_last_message(chat_id, message.id)

            logger.info(
                f"Policy decision for chat {chat_id}: {decision.action} - {decision.reason}"
            )

        if decision.action == "ignore":
            return

        if decision.action == "notify":
            await self._handle_watch_mode(message, chat_settings, sender_id)
        elif decision.action == "draft":
            await self._handle_draft_mode(message, chat_settings, sender_id)
        elif decision.action == "auto_reply":
            await self._handle_auto_reply(message, chat_settings)

    async def _handle_watch_mode(
        self,
        message: Message,
        chat_settings,
        sender_id: int | None,
    ) -> None:
        """
        Handle WATCH mode - notify owner without replying.

        Args:
            message: Incoming message.
            chat_settings: Chat settings.
            sender_id: Sender ID.
        """
        # Generate summary
        summary = await self.reply_generator.generate_summary(
            message_text=message.text or "",
            sender_name=str(sender_id) if sender_id else None,
        )

        # Notify owner via control bot
        await self.control_bot.notify_watch_message(
            chat_id=chat_settings.chat_id,
            chat_title=chat_settings.chat_title or f"Chat {chat_settings.chat_id}",
            sender_id=sender_id,
            message_text=message.text or "",
            summary=summary,
        )

        logger.info(f"Sent WATCH notification for chat {chat_settings.chat_id}")

    async def _handle_draft_mode(
        self,
        message: Message,
        chat_settings,
        sender_id: int | None,
    ) -> None:
        """
        Handle DRAFT mode - generate reply for approval.

        Args:
            message: Incoming message.
            chat_settings: Chat settings.
            pending_action_repo: Repository for pending actions.
            sender_id: Sender ID.
        """
        # Get context messages
        context_messages = await self._get_context_messages(
            chat_settings.chat_id, message.id
        )

        # Generate reply
        reply_result = await self.reply_generator.generate(
            incoming_message=message,
            context_messages=context_messages,
        )

        if not reply_result.success:
            logger.warning(f"Reply generation failed: {reply_result.error_message}")
            # Still create a draft with error message
            reply_text = reply_result.text or "[Failed to generate reply]"
        else:
            reply_text = reply_result.text

        # Create pending action
        with self.db.get_sync_session() as session:
            action = PendingActionRepo(session).create(
                action_type="reply",
                chat_id=chat_settings.chat_id,
                text=reply_text,
                reply_to_message_id=message.id,
            )

        # Send to owner for approval via control bot
        await self.control_bot.send_draft_for_approval(
            pending_action_id=action.id,
            chat_id=chat_settings.chat_id,
            chat_title=chat_settings.chat_title or f"Chat {chat_settings.chat_id}",
            original_message=message.text or "",
            sender_id=sender_id,
            reply_text=reply_text,
        )

        logger.info(f"Created draft action {action.id} for chat {chat_settings.chat_id}")

    async def _handle_auto_reply(
        self,
        message: Message,
        chat_settings,
    ) -> None:
        """
        Handle AUTO mode - reply automatically.

        Args:
            message: Incoming message.
            chat_settings: Chat settings.
            pending_action_repo: Repository for pending actions.
        """
        # Get context messages
        context_messages = await self._get_context_messages(
            chat_settings.chat_id, message.id
        )

        # Generate reply
        reply_result = await self.reply_generator.generate(
            incoming_message=message,
            context_messages=context_messages,
        )

        if not reply_result.success:
            logger.error(f"Auto-reply generation failed: {reply_result.error_message}")
            return

        # Send reply
        sent_message = await self.sender.send_reply(
            chat_id=chat_settings.chat_id,
            text=reply_result.text,
            reply_to_message_id=message.id,
            simulate_typing=True,
        )

        if sent_message:
            # Log the sent message
            with self.db.get_sync_session() as session:
                message_log_repo = MessageLogRepo(session)
                message_log_repo.create(
                    chat_id=chat_settings.chat_id,
                    message_id=sent_message.id,
                    sender_id=self.owner_id,
                    direction=MessageDirection.AGENT_SENT,
                    text=reply_result.text,
                )

                # Update cooldown
                self.cooldown_manager.record_reply(chat_settings.chat_id)
                chat_settings_repo = ChatSettingsRepo(session)
                chat_settings_repo.update_last_agent_reply(chat_settings.chat_id)

            logger.info(f"Auto-reply sent to chat {chat_settings.chat_id}")

    async def _get_context_messages(
        self,
        chat_id: int,
        current_message_id: int,
    ) -> list[Message]:
        """
        Get recent messages for context.

        Args:
            chat_id: Chat ID.
            current_message_id: Current message ID.

        Returns:
            List of recent messages.
        """
        try:
            messages = await self.client.get_messages(
                entity=chat_id,
                limit=self.settings.max_context_messages,
                max_id=current_message_id - 1,  # Exclude current message
            )
            return list(messages) if messages else []
        except Exception as e:
            logger.error(f"Failed to get context messages: {e}")
            return []


def setup_incoming_handlers(
    settings: Settings,
    db: Database,
    client: TelegramClient,
    control_bot: ControlBot,
    llm_client: LLMClient,
) -> IncomingMessageHandler:
    """
    Set up incoming message handlers.

    Args:
        settings: Application settings.
        db: Database instance.
        client: Telethon client.
        control_bot: Control bot instance.
        llm_client: LLM client instance.

    Returns:
        Configured IncomingMessageHandler.
    """
    handler = IncomingMessageHandler(
        settings=settings,
        db=db,
        client=client,
        control_bot=control_bot,
        llm_client=llm_client,
    )
    handler.register_handlers()
    return handler
