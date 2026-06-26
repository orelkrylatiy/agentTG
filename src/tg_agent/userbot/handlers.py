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
            events.NewMessage(),
        )
        logger.info("Incoming message handler registered")

    async def _on_new_message(self, event: events.NewMessage) -> None:
        try:
            await self._handle_message(event)
        except Exception as e:
            logger.exception(f"Unhandled error in message handler: {e}")

    async def _handle_message(self, event: events.NewMessage) -> None:
        message = event.message
        chat_id = event.chat_id
        sender_id = event.sender_id

        logger.debug(f"Event: chat={chat_id} sender={sender_id} out={message.out}")

        # Skip messages from self
        if message.out:
            return

        # Skip messages from bots
        if event.sender and getattr(event.sender, "bot", False):
            logger.debug(f"Skipping bot message from {sender_id}")
            return

        # Skip the control bot's own chat
        control_bot_id = int(self.settings.control_bot_token.split(":")[0])
        if chat_id == control_bot_id or sender_id == control_bot_id:
            logger.debug(f"Skipping control bot chat/message")
            return

        # Skip messages from broadcast channels (can't reply there anyway)
        from telethon.tl.types import Chat, Channel
        _sender_obj = getattr(event, "sender", None)
        if isinstance(_sender_obj, Channel) and not getattr(_sender_obj, "megagroup", False):
            logger.debug(f"Skipping broadcast channel message from {sender_id}")
            return

        # In group/supergroup chats only respond if mentioned or replied to
        _chat_obj = getattr(event, "chat", None)
        is_group = isinstance(_chat_obj, (Chat, Channel)) and getattr(_chat_obj, "megagroup", False) or isinstance(_chat_obj, Chat)
        if is_group:
            me = await event.client.get_me()
            mentioned = message.mentioned  # Telegram sets this when @username is in text
            reply_to_self = (
                message.reply_to
                and hasattr(message.reply_to, "reply_to_msg_id")
                and await self._is_reply_to_self(event, me.id)
            )
            if not mentioned and not reply_to_self:
                logger.debug(f"Group message without mention/reply, skipping")
                return

        logger.info(f"New message in chat {chat_id} from {sender_id}")

        try:
            _chat = await event.get_chat()
        except Exception:
            _chat = getattr(event, "chat", None)
        chat_title = getattr(_chat, "title", None) or " ".join(filter(None, [
            getattr(_chat, "first_name", None),
            getattr(_chat, "last_name", None),
        ])) or None
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
            # Extract needed fields before session closes
            chat_id_val = chat_settings.chat_id
            chat_title_val = chat_settings.chat_title

        if decision.action == "ignore":
            return

        if decision.action == "notify":
            await self._handle_watch_mode(message, chat_id_val, chat_title_val, sender_id)
        elif decision.action == "draft":
            await self._handle_draft_mode(message, chat_id_val, chat_title_val, sender_id)
        elif decision.action == "auto_reply":
            await self._handle_auto_reply(message, chat_id_val)

    async def _handle_watch_mode(
        self,
        message: Message,
        chat_id: int,
        chat_title: str | None,
        sender_id: int | None,
    ) -> None:
        summary = await self.reply_generator.generate_summary(
            message_text=message.text or "",
            sender_name=str(sender_id) if sender_id else None,
        )
        await self.control_bot.notify_watch_message(
            chat_id=chat_id,
            chat_title=chat_title or f"Chat {chat_id}",
            sender_id=sender_id,
            message_text=message.text or "",
            summary=summary,
        )
        logger.info(f"Sent WATCH notification for chat {chat_id}")

    async def _handle_draft_mode(
        self,
        message: Message,
        chat_id: int,
        chat_title: str | None,
        sender_id: int | None,
    ) -> None:
        context_messages = await self._get_context_messages(chat_id, message.id)

        reply_result = await self.reply_generator.generate(
            incoming_message=message,
            context_messages=context_messages,
        )

        if not reply_result.success:
            logger.warning(f"Reply generation failed: {reply_result.error_message}")
            reply_text = reply_result.text or "[Failed to generate reply]"
        else:
            reply_text = reply_result.text

        with self.db.get_sync_session() as session:
            action = PendingActionRepo(session).create(
                action_type="reply",
                chat_id=chat_id,
                text=reply_text,
                reply_to_message_id=message.id,
            )
            action_id = action.id

        await self.control_bot.send_draft_for_approval(
            pending_action_id=action_id,
            chat_id=chat_id,
            chat_title=chat_title or f"Chat {chat_id}",
            original_message=message.text or "",
            sender_id=sender_id,
            reply_text=reply_text,
        )
        logger.info(f"Created draft action {action_id} for chat {chat_id}")

    async def _handle_auto_reply(
        self,
        message: Message,
        chat_id: int,
    ) -> None:
        context_messages = await self._get_context_messages(chat_id, message.id)

        # Generate reply
        reply_result = await self.reply_generator.generate(
            incoming_message=message,
            context_messages=context_messages,
        )

        if not reply_result.success:
            logger.error(f"Auto-reply generation failed: {reply_result.error_message}")
            return

        sent_message = await self.sender.send_reply(
            chat_id=chat_id,
            text=reply_result.text,
            reply_to_message_id=message.id,
            simulate_typing=True,
        )

        if sent_message:
            with self.db.get_sync_session() as session:
                MessageLogRepo(session).create(
                    chat_id=chat_id,
                    message_id=sent_message.id,
                    sender_id=self.owner_id,
                    direction=MessageDirection.AGENT_SENT,
                    text=reply_result.text,
                )
                self.cooldown_manager.record_reply(chat_id)
                ChatSettingsRepo(session).update_last_agent_reply(chat_id)

            logger.info(f"Auto-reply sent to chat {chat_id}")

    async def _is_reply_to_self(self, event, my_id: int) -> bool:
        """Check if message is a reply to one of our messages."""
        try:
            replied = await event.message.get_reply_message()
            return replied is not None and replied.sender_id == my_id
        except Exception:
            return False

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
            return list(reversed(messages)) if messages else []
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
