"""
Channel message handler - monitors specified channels and notifies owner.
"""

from telethon import TelegramClient, events

from tg_agent.config import Settings
from tg_agent.control_bot import ControlBot
from tg_agent.logging import get_logger

logger = get_logger(__name__)


class ChannelHandler:
    def __init__(self, settings: Settings, client: TelegramClient, control_bot: ControlBot):
        self.settings = settings
        self.client = client
        self.control_bot = control_bot

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
