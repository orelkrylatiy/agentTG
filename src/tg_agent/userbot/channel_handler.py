"""
Channel message handler - monitors specified channels, notifies owner,
and auto-sends personalized outreach DMs to contacts found in posts.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from telethon import TelegramClient, events

from tg_agent.agent.llm import LLMClient
from tg_agent.config import Settings
from tg_agent.control_bot import ControlBot
from tg_agent.logging import get_logger
from tg_agent.policy.modes import ChatMode
from tg_agent.storage.models import ChatSettings
from tg_agent.storage.repositories import ChatSettingsRepo

logger = get_logger(__name__)

OUTREACH_SYSTEM = """Ты — фронтенд-разработчик с 5 годами опыта, ищешь новую работу.
Пишешь первое сообщение рекрутеру или работодателю из канала вакансий.
Напиши короткое живое сообщение (2-3 предложения) на русском:
— упомяни конкретную деталь из вакансии (название роли, компанию или технологию)
— скажи что ты frontend-разработчик с 5 годами опыта и готов скинуть резюме
— спроси актуальна ли вакансия
Только текст сообщения — без кавычек, заголовков и пояснений."""

_CONTACT_RE = re.compile(r'(?:@([a-zA-Z0-9_]{4,32})|t\.me/([a-zA-Z0-9_]{4,32}))')


class ChannelHandler:
    def __init__(
        self,
        settings: Settings,
        client: TelegramClient,
        control_bot: ControlBot,
        db,  # Database instance for updating chat settings
        llm_client: LLMClient | None = None,
    ):
        self.settings = settings
        self.client = client
        self.control_bot = control_bot
        self.db = db
        self.llm_client = llm_client
        self._contacted_path = Path("data/contacted.json")
        self._contacted: set[str] = self._load_contacted()

    def _load_contacted(self) -> set[str]:
        try:
            return set(json.loads(self._contacted_path.read_text()))
        except Exception:
            return set()

    def _save_contacted(self) -> None:
        self._contacted_path.write_text(json.dumps(sorted(self._contacted)))

    def register_handlers(self) -> None:
        channel_ids = self.settings.monitored_channel_ids
        if not channel_ids:
            logger.info("No monitored channels configured")
            return

        self.client.add_event_handler(
            self._on_channel_post,
            events.NewMessage(chats=channel_ids),
        )
        logger.info(f"Channel handler registered for {len(channel_ids)} channel(s): {channel_ids}")

    async def _on_channel_post(self, event: events.NewMessage) -> None:
        message = event.message
        if not message.text:
            return

        chat = await event.get_chat()
        channel_title = getattr(chat, "title", f"Channel {event.chat_id}")

        # Forward to owner
        text = (
            f"📢 <b>{channel_title}</b>\n\n"
            f"{message.text[:1000]}"
        )
        if len(message.text) > 1000:
            text += "\n\n<i>... (сообщение обрезано)</i>"

        await self.control_bot.send_message(
            chat_id=self.settings.owner_telegram_id,
            text=text,
            parse_mode="HTML",
        )
        logger.info(f"Forwarded channel post from {event.chat_id} ({channel_title})")

        # Auto-outreach if LLM is available
        if self.llm_client:
            await self._try_outreach(message.text)

    async def _try_outreach(self, post_text: str) -> None:
        matches = _CONTACT_RE.findall(post_text)
        usernames = [m[0] or m[1] for m in matches if m[0] or m[1]]
        usernames = list(dict.fromkeys(usernames))  # dedup

        for username in usernames:
            if username.lower() in self._contacted:
                logger.info(f"Outreach: @{username} already contacted, skipping")
                continue

            logger.info(f"Outreach: generating DM for @{username}")
            resp = await self.llm_client.generate_reply(
                messages=[{"role": "user", "content": f"Вакансия:\n{post_text[:800]}"}],
                system_prompt=OUTREACH_SYSTEM,
            )

            if not resp.success or not resp.content:
                logger.warning(f"Outreach: LLM failed for @{username}: {resp.error_message}")
                continue

            try:
                sent_message = await self.client.send_message(username, resp.content)
                chat_id = sent_message.chat_id
                
                self._contacted.add(username.lower())
                self._save_contacted()
                
                # Set AUTO mode + trusted for this chat so bot can auto-reply to responses
                logger.info(f"Outreach: saving AUTO+trusted settings for chat_id={chat_id}")
                with self.db.get_sync_session() as session:
                    chat_repo = ChatSettingsRepo(session)
                    # Create or get settings with AUTO mode and trusted=True from the start
                    chat = chat_repo.get_by_chat_id(chat_id)
                    if chat is None:
                        # Create new with correct settings
                        chat = ChatSettings(
                            chat_id=chat_id,
                            mode=ChatMode.AUTO,
                            is_trusted=True,
                            chat_title=username,
                        )
                        session.add(chat)
                        session.commit()
                        session.refresh(chat)
                        logger.info(f"Outreach: CREATED chat {chat_id} with mode=AUTO, trusted=True")
                    else:
                        # Update existing
                        old_mode = chat.mode
                        old_trusted = chat.is_trusted
                        chat.mode = ChatMode.AUTO
                        chat.is_trusted = True
                        chat.updated_at = datetime.utcnow()
                        session.commit()
                        session.refresh(chat)
                        logger.info(f"Outreach: UPDATED chat {chat_id}: mode {old_mode.value}→AUTO, trusted {old_trusted}→True")

                logger.info(f"Outreach: sent to @{username}: {resp.content!r} (chat {chat_id} set to AUTO+trusted)")
            except Exception as e:
                logger.warning(f"Outreach: failed to send to @{username}: {e}")
