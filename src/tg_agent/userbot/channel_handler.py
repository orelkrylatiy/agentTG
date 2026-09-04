"""
Channel message handler - monitors configured channels, notifies the owner,
and can run explicitly-authorized automatic outreach workflows.
"""

import re
from datetime import datetime, timedelta

from telethon import TelegramClient, events

from tg_agent.agent.llm import LLMClient
from tg_agent.agent.prompts import PromptManager
from tg_agent.config import Settings
from tg_agent.control_bot import ControlBot
from tg_agent.logging import get_logger
from tg_agent.policy.modes import ChatMode
from tg_agent.storage.models import ChatSettings, MessageDirection
from tg_agent.storage.repositories import (
    ChatSettingsRepo,
    GlobalStateRepo,
    MessageLogRepo,
    MonitoredChannelRepo,
    OutreachContactRepo,
)

logger = get_logger(__name__)

_CONTACT_RE = re.compile(r"(?:@([a-zA-Z0-9_]{4,32})|t\.me/([a-zA-Z0-9_]{4,32}))")


class ChannelHandler:
    def __init__(
        self,
        settings: Settings,
        client: TelegramClient,
        control_bot: ControlBot,
        db,
        llm_client: LLMClient | None = None,
        prompt_manager: PromptManager | None = None,
    ):
        self.settings = settings
        self.client = client
        self.control_bot = control_bot
        self.db = db
        self.llm_client = llm_client
        self.prompt_manager = prompt_manager or PromptManager(settings)
        # Compatibility/metrics only. Durable deduplication lives in SQLite.
        self._contacted: set[str] = set()

    def register_handlers(self) -> None:
        self.client.add_event_handler(self._on_channel_post, events.NewMessage())
        with self.db.get_sync_session() as session:
            channel_count = len(MonitoredChannelRepo(session).get_all())
        logger.info(
            f"Channel handler registered for {channel_count} configured channel(s)"
        )

    async def _on_channel_post(self, event: events.NewMessage) -> None:
        message = event.message
        if not message.text or event.chat_id is None:
            return

        with self.db.get_sync_session() as session:
            agent_enabled = GlobalStateRepo(session).get_bool(
                "agent_enabled",
                self.settings.agent_global_enabled,
            )
            channel_config = MonitoredChannelRepo(session).get_by_id(event.chat_id)

        if not agent_enabled:
            logger.debug("Agent paused; skipping channel processing")
            return
        if not channel_config or not channel_config.enabled:
            return

        keywords = channel_config.keywords.split(",") if channel_config.keywords else []
        if keywords and not any(kw.lower() in message.text.lower() for kw in keywords):
            logger.debug(
                f"Message does not match keywords for channel {event.chat_id}"
            )
            return

        chat = await event.get_chat()
        channel_title = channel_config.channel_title or getattr(
            chat,
            "title",
            f"Channel {event.chat_id}",
        )

        preview_len = 400
        text_preview = message.text[:preview_len]
        truncated = len(message.text) > preview_len

        link_id = str(event.chat_id)
        if link_id.startswith("-100"):
            link_id = link_id[4:]
        channel_link = f"https://t.me/c/{link_id}/{message.id}"

        text = (
            f"{text_preview}"
            f"{'... (обрезано)' if truncated else ''}"
            f"\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📢 <b>{channel_title}</b> | <a href='{channel_link}'>оригинал</a>"
        )
        await self.control_bot.send_message(
            chat_id=self.settings.owner_telegram_id,
            text=text,
            parse_mode="HTML",
        )
        logger.info(
            f"Forwarded channel post from {event.chat_id} ({channel_title})"
        )

        if channel_config.auto_outreach and self.llm_client:
            await self._try_outreach(
                post_text=message.text,
                channel_id=event.chat_id,
                max_per_hour=channel_config.max_posts_per_hour,
            )

    async def _try_outreach(
        self,
        post_text: str,
        channel_id: int,
        max_per_hour: int = 60,
        max_contacts: int | None = None,
    ) -> list[str]:
        """Contact new usernames from a post and return successfully sent usernames."""
        matches = _CONTACT_RE.findall(post_text)
        usernames = [match[0] or match[1] for match in matches if match[0] or match[1]]
        usernames = list(dict.fromkeys(usernames))
        if max_contacts is not None:
            usernames = usernames[: max(0, max_contacts)]
        if not usernames:
            return []

        if self.llm_client is None:
            return []

        system_prompt = self.prompt_manager.get_outreach_prompt(channel_id)
        hour_ago = datetime.utcnow() - timedelta(hours=1)
        sent_usernames: list[str] = []

        for username in usernames:
            with self.db.get_sync_session() as session:
                if not GlobalStateRepo(session).get_bool(
                    "agent_enabled",
                    self.settings.agent_global_enabled,
                ):
                    logger.info("Outreach stopped because agent was paused")
                    return sent_usernames

                contact_repo = OutreachContactRepo(session)
                sent_last_hour = contact_repo.count_sent_since(channel_id, hour_ago)
                if sent_last_hour >= max_per_hour:
                    logger.info(
                        f"Outreach send limit reached for channel {channel_id}: "
                        f"{sent_last_hour}/{max_per_hour}"
                    )
                    return sent_usernames

                claimed = contact_repo.claim(username, channel_id)
                if claimed is None:
                    logger.info(
                        f"Outreach: @{username} already sent/pending, skipping"
                    )
                    continue

            logger.info(f"Outreach: generating DM for @{username}")
            resp = await self.llm_client.generate_reply(
                messages=[
                    {
                        "role": "user",
                        "content": f"Вакансия:\n{post_text[:800]}",
                    }
                ],
                system_prompt=system_prompt,
            )

            if not resp.success or not resp.content:
                error = resp.error_message or "empty LLM response"
                with self.db.get_sync_session() as session:
                    OutreachContactRepo(session).mark_failed(username, error)
                logger.warning(f"Outreach: LLM failed for @{username}: {error}")
                continue

            try:
                sent_message = await self.client.send_message(username, resp.content)
                chat_id = sent_message.chat_id

                with self.db.get_sync_session() as session:
                    OutreachContactRepo(session).mark_sent(
                        username,
                        sent_message.id,
                    )
                    MessageLogRepo(session).create(
                        chat_id=chat_id,
                        message_id=sent_message.id,
                        sender_id=self.settings.owner_telegram_id,
                        direction=MessageDirection.AGENT_SENT,
                        text=resp.content,
                    )

                    chat_repo = ChatSettingsRepo(session)
                    chat = chat_repo.get_by_chat_id(chat_id)
                    if chat is None:
                        chat = ChatSettings(
                            chat_id=chat_id,
                            mode=ChatMode.DRAFT,
                            is_trusted=True,
                            chat_title=username,
                        )
                        session.add(chat)
                        session.commit()
                        session.refresh(chat)
                    else:
                        chat.mode = ChatMode.DRAFT
                        chat.is_trusted = True
                        chat.updated_at = datetime.utcnow()
                        session.commit()
                        session.refresh(chat)

                normalized = username.lower()
                self._contacted.add(normalized)
                sent_usernames.append(normalized)
                logger.info(
                    f"Outreach: sent to @{username} and set chat {chat_id} "
                    "to DRAFT+trusted"
                )
            except Exception as exc:
                with self.db.get_sync_session() as session:
                    OutreachContactRepo(session).mark_failed(username, str(exc))
                logger.warning(f"Outreach: failed to send to @{username}: {exc}")

        return sent_usernames
