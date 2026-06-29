"""
Incoming message handlers for Telethon userbot.
"""

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat
from telethon.tl.types import Message

from tg_agent.agent.llm import LLMClient
from tg_agent.agent.reply import ReplyGenerator
from tg_agent.config import Settings
from tg_agent.control_bot import ControlBot
from tg_agent.logging import get_logger
from tg_agent.policy.cooldown import CooldownManager
from tg_agent.policy.filters import MessageFilter
from tg_agent.policy.gate import PolicyDecision, PolicyGate
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

        # Debounce: accumulate messages per chat, reply once after 3s silence
        self._pending: dict[int, list] = defaultdict(list)
        self._timers: dict[int, asyncio.Task] = {}
        self._debounce_seconds = 3.0
        self._processing_messages: set[tuple[int, int]] = set()
        self._processing_lock = asyncio.Lock()
        self._me_id: int | None = None

    def register_handlers(self) -> None:
        """Register event handlers with the client."""
        self.client.add_event_handler(
            self._on_new_message,
            events.NewMessage(),
        )
        logger.info("Incoming message handler registered")

    async def _on_new_message(self, event: events.NewMessage) -> None:
        try:
            await self._filter_and_enqueue(event)
        except Exception as e:
            logger.exception(f"Unhandled error in message handler: {e}")

    async def _filter_and_enqueue(self, event: events.NewMessage) -> None:
        """Run early filters, then debounce-enqueue the event."""
        message = event.message
        chat_id = event.chat_id
        sender_id = event.sender_id

        if not await self._passes_early_filters(
            message=message,
            chat_id=chat_id,
            sender_id=sender_id,
            chat_obj=getattr(event, "chat", None),
            sender_obj=getattr(event, "sender", None),
        ):
            return

        # Passed all filters — debounce
        self._pending[chat_id].append(event)
        if chat_id in self._timers:
            self._timers[chat_id].cancel()
        self._timers[chat_id] = asyncio.create_task(
            self._flush_after_delay(chat_id)
        )

    async def _flush_after_delay(self, chat_id: int) -> None:
        await asyncio.sleep(self._debounce_seconds)
        events_batch = self._pending.pop(chat_id, [])
        self._timers.pop(chat_id, None)
        if not events_batch:
            return
        # Use the last event as the canonical one; combine all texts
        last_event = events_batch[-1]
        if len(events_batch) > 1:
            combined = "\n".join(
                e.message.text for e in events_batch if e.message.text
            )
            last_event.message.message = combined  # patch text for processing
        await self._handle_message(last_event)

    async def _handle_message(self, event: events.NewMessage) -> None:
        await self._handle_message_object(
            message=event.message,
            chat_id=event.chat_id,
            sender_id=event.sender_id,
            chat_obj=getattr(event, "chat", None),
        )

    async def _handle_message_object(
        self,
        message: Message,
        chat_id: int,
        sender_id: int | None,
        *,
        chat_obj=None,
        is_catchup: bool = False,
    ) -> bool:
        message_id = getattr(message, "id", None)
        if message_id is None:
            return False

        key = (chat_id, message_id)
        async with self._processing_lock:
            if key in self._processing_messages:
                logger.info(f"Skipping duplicate in-flight message {message_id} in chat {chat_id}")
                return False
            self._processing_messages.add(key)

        try:
            source = "catch-up" if is_catchup else "live"
            logger.info(f"Processing {source} message {message_id} in chat {chat_id} from {sender_id}")

            # Mark message as read
            try:
                await self.client.send_read_acknowledge(chat_id, max_id=message.id)
            except Exception:
                pass

            resolved_chat = chat_obj
            if resolved_chat is None:
                try:
                    resolved_chat = await message.get_chat()
                except Exception:
                    resolved_chat = None

            chat_title = getattr(resolved_chat, "title", None) or " ".join(
                filter(
                    None,
                    [
                        getattr(resolved_chat, "first_name", None),
                        getattr(resolved_chat, "last_name", None),
                    ],
                )
            ) or None

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

                if message_log_repo.exists(
                    chat_id=chat_id,
                    message_id=message.id,
                    direction=MessageDirection.INCOMING,
                ):
                    logger.info(f"Skipping already logged message {message.id} in chat {chat_id}")
                    return False

                if (
                    chat_settings.last_incoming_message_id is not None
                    and message.id <= chat_settings.last_incoming_message_id
                ):
                    logger.info(
                        f"Skipping stale message {message.id} in chat {chat_id}; "
                        f"last seen is {chat_settings.last_incoming_message_id}"
                    )
                    return False

                decision = self.policy_gate.evaluate(
                    chat_settings=chat_settings,
                    sender_id=sender_id or 0,
                    message_text=message.text or "",
                    last_message_sender_id=previous_sender_id,
                )
                if is_catchup:
                    decision = self._normalize_catchup_decision(decision, message)

                logger.info(
                    f"Chat {chat_id}: mode={chat_settings.mode.value}, "
                    f"trusted={chat_settings.is_trusted}, "
                    f"policy_action={decision.action}, requires_approval={decision.requires_approval}"
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
                chat_id_val = chat_settings.chat_id
                chat_title_val = chat_settings.chat_title

            if decision.action == "ignore":
                return False

            if decision.action == "notify":
                await self._handle_watch_mode(message, chat_id_val, chat_title_val, sender_id)
            elif decision.action == "draft":
                await self._handle_draft_mode(message, chat_id_val, chat_title_val, sender_id)
            elif decision.action == "auto_reply":
                await self._handle_auto_reply(message, chat_id_val)
            return True
        finally:
            async with self._processing_lock:
                self._processing_messages.discard(key)

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

    async def catch_up_missed_messages(self) -> int:
        """Process the latest missed relevant message per recent dialog."""
        if not self.settings.startup_catchup_enabled:
            logger.info("Startup catch-up disabled")
            return 0

        logger.info("Starting startup catch-up sync...")
        processed = 0
        dialogs = await self.client.get_dialogs(
            limit=self.settings.startup_catchup_dialog_limit
        )

        for dialog in dialogs:
            try:
                if await self._catch_up_dialog(dialog):
                    processed += 1
            except Exception as e:
                logger.exception(
                    f"Failed to catch up dialog {getattr(dialog, 'id', None)}: {e}"
                )

        logger.info(f"Startup catch-up finished: processed {processed} dialog(s)")
        return processed

    async def _catch_up_dialog(self, dialog) -> bool:
        chat_id = getattr(dialog, "id", None)
        if chat_id is None:
            return False

        unread_count = int(getattr(dialog, "unread_count", 0) or 0)
        latest_message = getattr(dialog, "message", None)
        latest_message_id = getattr(latest_message, "id", 0) or 0

        with self.db.get_sync_session() as session:
            chat_settings = ChatSettingsRepo(session).get_by_chat_id(chat_id)
            last_seen_id = chat_settings.last_incoming_message_id if chat_settings else None

        should_sync = unread_count > 0 or (
            last_seen_id is not None and latest_message_id > last_seen_id
        )
        if not should_sync:
            return False

        fetch_kwargs = {
            "entity": dialog.entity,
            "limit": self.settings.startup_catchup_messages_per_chat,
        }
        if last_seen_id:
            fetch_kwargs["min_id"] = last_seen_id

        messages = await self.client.get_messages(**fetch_kwargs)
        if not messages:
            return False

        target_message = None
        target_chat = None
        for message in messages:
            if message is None:
                continue
            if last_seen_id is not None and message.id <= last_seen_id:
                continue
            chat_obj = await message.get_chat()
            sender_obj = await message.get_sender()
            if not await self._passes_early_filters(
                message=message,
                chat_id=chat_id,
                sender_id=getattr(message, "sender_id", None),
                chat_obj=chat_obj,
                sender_obj=sender_obj,
            ):
                continue
            if target_message is None or message.id > target_message.id:
                target_message = message
                target_chat = chat_obj

        if target_message is None:
            return False

        return await self._handle_message_object(
            message=target_message,
            chat_id=chat_id,
            sender_id=getattr(target_message, "sender_id", None),
            chat_obj=target_chat,
            is_catchup=True,
        )

    async def _passes_early_filters(
        self,
        *,
        message: Message,
        chat_id: int | None,
        sender_id: int | None,
        chat_obj,
        sender_obj,
    ) -> bool:
        """Apply the same coarse Telegram-side filters for live and catch-up paths."""
        if chat_id is None or message.out:
            return False
        if sender_obj and getattr(sender_obj, "bot", False):
            return False

        control_bot_id = int(self.settings.control_bot_token.split(":")[0])
        if chat_id == control_bot_id or sender_id == control_bot_id:
            return False

        if isinstance(sender_obj, Channel) and not getattr(sender_obj, "megagroup", False):
            return False

        is_group = (
            isinstance(chat_obj, (Chat, Channel)) and getattr(chat_obj, "megagroup", False)
        ) or isinstance(chat_obj, Chat)
        if is_group:
            me_id = await self._get_me_id()
            mentioned = bool(getattr(message, "mentioned", False))
            reply_to_self = (
                message.reply_to
                and hasattr(message.reply_to, "reply_to_msg_id")
                and await self._is_reply_to_self_message(message, me_id)
            )
            if not mentioned and not reply_to_self:
                return False

        return True

    async def _get_me_id(self) -> int:
        if self._me_id is None:
            me = await self.client.get_me()
            self._me_id = me.id
        return self._me_id

    async def _is_reply_to_self_message(self, message: Message, my_id: int) -> bool:
        """Check if message is a reply to one of our messages."""
        try:
            replied = await message.get_reply_message()
            return replied is not None and replied.sender_id == my_id
        except Exception:
            return False

    def _normalize_catchup_decision(
        self,
        decision: PolicyDecision,
        message: Message,
    ) -> PolicyDecision:
        """Avoid automatic replies to stale startup backlog messages."""
        if decision.action != "auto_reply":
            return decision

        message_date = getattr(message, "date", None)
        if message_date is None:
            return PolicyDecision(
                should_process=True,
                action="draft",
                reason="Catch-up message without timestamp requires approval",
                requires_approval=True,
            )

        max_age = timedelta(
            minutes=self.settings.startup_catchup_auto_reply_max_age_minutes
        )
        now = datetime.now(timezone.utc)
        if message_date.tzinfo is None:
            message_date = message_date.replace(tzinfo=timezone.utc)

        if now - message_date <= max_age:
            return decision

        return PolicyDecision(
            should_process=True,
            action="draft",
            reason="Stale catch-up message requires approval",
            requires_approval=True,
        )

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
