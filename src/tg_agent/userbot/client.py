"""
Telethon userbot client.
"""

from pathlib import Path

from telethon import TelegramClient

from tg_agent.config import Settings
from tg_agent.logging import get_logger

logger = get_logger(__name__)


class UserbotClient:
    """
    Telethon userbot client wrapper.

    Manages connection to Telegram user account.
    """

    def __init__(self, settings: Settings):
        """
        Initialize userbot client.

        Args:
            settings: Application settings.
        """
        self.settings = settings
        self._client: TelegramClient | None = None

    @property
    def client(self) -> TelegramClient:
        """Get or create Telegram client."""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _create_client(self) -> TelegramClient:
        """
        Create and configure Telegram client.

        Returns:
            Configured TelegramClient instance.
        """
        # Ensure data directory exists
        session_path = Path(self.settings.telethon_session_name)
        session_dir = session_path.parent
        session_dir.mkdir(parents=True, exist_ok=True)

        # Create client
        client = TelegramClient(
            str(session_path),
            self.settings.tg_api_id,
            self.settings.tg_api_hash,
        )

        logger.info("Telethon client created")
        return client

    async def start(self) -> None:
        """
        Start the userbot client.

        Will prompt for phone code if not already authorized.
        """
        logger.info("Starting userbot client...")

        # Start client
        await self.client.start(
            phone=self.settings.tg_phone,
            code_callback=self._get_code,
            password_callback=self._get_password,
        )

        # Get me info
        me = await self.client.get_me()
        logger.info(f"Userbot started as @{me.username} (ID: {me.id})")

        # Verify owner ID matches
        if me.id != self.settings.owner_telegram_id:
            logger.warning(
                f"Owner ID mismatch: session user {me.id} != "
                f"configured {self.settings.owner_telegram_id}"
            )

    async def _get_code(self) -> str:
        """
        Get 2FA code from user.

        Note: In production, this should be handled more securely.
        """
        logger.warning("Please enter the login code sent to your Telegram")
        # For non-interactive mode, we rely on existing session
        # In interactive mode, this would prompt for input
        return input("Enter login code: ")

    async def _get_password(self) -> str:
        """
        Get 2FA password from user.

        Note: In production, this should be handled more securely.
        """
        logger.warning("Please enter your 2FA password")
        return input("Enter 2FA password: ")

    async def stop(self) -> None:
        """Stop the userbot client."""
        if self._client is not None:
            await self._client.disconnect()
            logger.info("Userbot client stopped")

    async def get_me(self):
        """Get current user info."""
        return await self.client.get_me()

    async def get_entity(self, entity):
        """
        Get entity (user, chat, channel) by ID or username.

        Args:
            entity: Entity ID, username, or phone number.

        Returns:
            Entity object or None.
        """
        try:
            return await self.client.get_entity(entity)
        except Exception as e:
            logger.error(f"Failed to get entity {entity}: {e}")
            return None

    async def get_dialogs(self, limit: int = 50):
        """
        Get recent dialogs (chats).

        Args:
            limit: Maximum number of dialogs to fetch.

        Returns:
            List of dialogs.
        """
        return await self.client.get_dialogs(limit=limit)

    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._client is not None and self._client.is_connected()
