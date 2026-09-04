"""Run a one-shot scan using the same outreach policy/state as the live agent.

Usage:
    python outreach.py [N] [CHANNEL_ID]

Only channels explicitly configured with ``auto_outreach`` are allowed to send.
The global ``agent_enabled`` SQLite state is respected, deduplication is durable,
and rate limits are shared with live channel monitoring.
"""

import asyncio
import os
import sys

sys.path.insert(0, "src")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from tg_agent.agent.llm import LLMClient
from tg_agent.agent.prompts import PromptManager
from tg_agent.config import Settings
from tg_agent.storage.db import get_db
from tg_agent.storage.repositories import GlobalStateRepo, MonitoredChannelRepo
from tg_agent.userbot.channel_handler import ChannelHandler
from tg_agent.userbot.client import UserbotClient


async def main() -> None:
    settings = Settings()
    db = get_db(
        settings.database_url,
        default_agent_enabled=settings.agent_global_enabled,
        default_chat_mode=settings.default_chat_mode,
    )
    await db.init_db()

    with db.get_sync_session() as session:
        enabled = GlobalStateRepo(session).get_bool(
            "agent_enabled",
            settings.agent_global_enabled,
        )
        channels = MonitoredChannelRepo(session).get_all()

    if not enabled:
        print("❌ Agent is paused. Use /resume before running automatic outreach.")
        return

    if len(sys.argv) > 2:
        try:
            target_id = int(sys.argv[2])
        except ValueError:
            print(f"❌ Invalid channel ID: {sys.argv[2]}")
            return
        channels = [channel for channel in channels if channel.channel_id == target_id]

    if not channels:
        print("❌ No matching DB-backed monitored channels configured")
        return

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    limit = max(1, min(limit, 50))

    userbot = UserbotClient(settings)
    await userbot.start()
    try:
        llm = LLMClient(settings)
        handler = ChannelHandler(
            settings=settings,
            client=userbot.client,
            control_bot=None,
            db=db,
            llm_client=llm,
            prompt_manager=PromptManager(settings),
        )

        for channel in channels:
            if not channel.auto_outreach:
                print(
                    f"⏭️ {channel.channel_title or channel.channel_id}: "
                    "auto_outreach is disabled"
                )
                continue

            messages = await userbot.client.get_messages(
                channel.channel_id,
                limit=limit,
            )
            keywords = (
                [item.strip().lower() for item in channel.keywords.split(",") if item.strip()]
                if channel.keywords
                else []
            )

            print(
                f"🔍 {channel.channel_title or channel.channel_id}: "
                f"scanning {len(messages)} post(s)"
            )
            before = len(handler._contacted)
            for message in reversed(messages):
                text = message.text or ""
                if not text:
                    continue
                if keywords and not any(keyword in text.lower() for keyword in keywords):
                    continue
                await handler._try_outreach(
                    post_text=text,
                    channel_id=channel.channel_id,
                    max_per_hour=channel.max_posts_per_hour,
                )

            sent = len(handler._contacted) - before
            print(f"✅ {channel.channel_title or channel.channel_id}: sent {sent}")
    finally:
        await userbot.stop()


if __name__ == "__main__":
    asyncio.run(main())
