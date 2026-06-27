"""
Main entry point for Telegram AI Userbot Agent.

Run with: python -m tg_agent.main
"""

import asyncio
import signal
import sys

from tg_agent.agent.llm import LLMClient
from tg_agent.config import Settings, get_settings
from tg_agent.control_bot import ControlBot, HITLManager
from tg_agent.control_bot.handlers import setup_control_handlers
from tg_agent.logging import get_logger, setup_logging
from tg_agent.storage.db import get_db
from tg_agent.userbot import UserbotClient
from tg_agent.userbot.channel_handler import ChannelHandler
from tg_agent.userbot.handlers import setup_incoming_handlers

logger = get_logger(__name__)


class Agent:
    """
    Main agent orchestrator.

    Manages lifecycle of:
    - Telethon userbot
    - aiogram control bot
    - Database
    - LLM client
    """

    def __init__(self, settings: Settings):
        """
        Initialize agent.

        Args:
            settings: Application settings.
        """
        self.settings = settings
        self.db = get_db(
            settings.database_url,
            default_agent_enabled=settings.agent_global_enabled,
            default_chat_mode=settings.default_chat_mode,
        )

        # Initialize components
        self.userbot = UserbotClient(settings)
        self.control_bot = ControlBot(settings)
        self.llm_client = LLMClient(settings)

        # Shutdown flag
        self._shutdown = False

    async def initialize(self) -> None:
        """Initialize all components."""
        logger.info("Initializing agent components...")

        # Setup logging
        setup_logging(self.settings)

        # Initialize database
        await self.db.init_db()
        logger.info("Database initialized")

        # Initialize control bot
        await self.control_bot.start()
        logger.info("Control bot initialized")

        # Initialize userbot
        await self.userbot.start()
        logger.info("Userbot initialized")

        # Create message sender for HITL
        from tg_agent.humanizer.delays import TypingDelaySimulator
        from tg_agent.userbot.sender import MessageSender

        sender = MessageSender(
            self.userbot.client,
            TypingDelaySimulator(),
        )

        # Setup HITL manager
        hitl_manager = HITLManager(
            settings=self.settings,
            db=self.db,
            control_bot=self.control_bot,
            sender=sender,
        )
        hitl_manager.register_handlers(self.control_bot.dispatcher)

        # Setup incoming message handlers
        setup_incoming_handlers(
            settings=self.settings,
            db=self.db,
            client=self.userbot.client,
            control_bot=self.control_bot,
            llm_client=self.llm_client,
        )

        # Setup channel monitoring
        channel_handler = ChannelHandler(
            settings=self.settings,
            client=self.userbot.client,
            control_bot=self.control_bot,
            db=self.db,
            llm_client=self.llm_client,
        )
        channel_handler.register_handlers()

        # Setup control bot handlers (after channel_handler so we can pass it)
        setup_control_handlers(
            dp=self.control_bot.dispatcher,
            settings=self.settings,
            db=self.db,
            control_bot=self.control_bot,
            userbot_client=self.userbot.client,
            channel_handler=channel_handler,
        )

        # LLM health check
        logger.info("Checking LLM connectivity...")
        llm_test = await self.llm_client.smoke_test()
        if llm_test.success:
            logger.info(f"LLM OK — {llm_test.provider.value} / {llm_test.model}")
        else:
            logger.warning(f"LLM UNAVAILABLE — {llm_test.error_message}. Agent will start but replies will fail until LLM is up.")

        logger.info("All components initialized successfully")

    async def run(self) -> None:
        """
        Run the agent.

        Runs both userbot and control bot concurrently.
        """
        logger.info("Starting agent...")

        # Create tasks for both bots
        userbot_task = asyncio.create_task(self._run_userbot())
        control_bot_task = asyncio.create_task(self._run_control_bot())

        # Wait for shutdown signal
        try:
            await asyncio.gather(userbot_task, control_bot_task)
        except asyncio.CancelledError:
            logger.info("Agent tasks cancelled")

    async def _run_userbot(self) -> None:
        """Run userbot event loop."""
        logger.info("Userbot event loop started")
        try:
            await self.userbot.client.run_until_disconnected()
        except asyncio.CancelledError:
            pass
        finally:
            logger.info("Userbot event loop stopped")

    async def _run_control_bot(self) -> None:
        """Run control bot polling."""
        logger.info("Control bot polling started")
        try:
            await self.control_bot.dispatcher.start_polling(
                self.control_bot.bot,
                allowed_updates=["message", "callback_query"],
            )
        except asyncio.CancelledError:
            pass
        finally:
            logger.info("Control bot polling stopped")

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutting down agent...")

        self._shutdown = True

        # Stop control bot
        await self.control_bot.stop()

        # Stop userbot
        await self.userbot.stop()

        logger.info("Agent shutdown complete")


async def main() -> None:
    """Main entry point."""
    # Load settings
    try:
        settings = get_settings()
    except Exception as e:
        print(f"❌ Failed to load settings: {e}", file=sys.stderr)
        print("\nMake sure to copy .env.example to .env and fill in required values:")
        print("  - TG_API_ID, TG_API_HASH, TG_PHONE")
        print("  - CONTROL_BOT_TOKEN")
        print("  - OWNER_TELEGRAM_ID")
        sys.exit(1)

    # Validate settings
    if settings.tg_api_hash == "replace_me" or settings.control_bot_token == "replace_me":
        print("❌ Please fill in required values in .env file", file=sys.stderr)
        print("  - TG_API_HASH")
        print("  - CONTROL_BOT_TOKEN")
        sys.exit(1)

    # Create agent
    agent = Agent(settings)

    # Setup signal handlers
    loop = asyncio.get_event_loop()

    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(agent.shutdown())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        # Initialize
        await agent.initialize()

        # Run
        await agent.run()

    except Exception as e:
        logger.exception(f"Agent error: {e}")
        await agent.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
