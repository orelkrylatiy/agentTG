"""
Channel message handler - monitors specified channels, notifies owner,
and auto-sends personalized outreach DMs to contacts found in posts.
"""

import json
import re
from pathlib import Path

from telethon import TelegramClient, events

from tg_agent.agent.llm import LLMClient
from tg_agent.config import Settings
from tg_agent.control_bot import ControlBot
from tg_agent.logging import get_logger

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
        llm_client: LLMClient | None = None,
    ):
        self.settings = settings
        self.client = client
        self.control_bot = control_bot
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
                await self.client.send_message(username, resp.content)
                self._contacted.add(username.lower())
                self._save_contacted()
                logger.info(f"Outreach: sent to @{username}: {resp.content!r}")
            except Exception as e:
                logger.warning(f"Outreach: failed to send to @{username}: {e}")
