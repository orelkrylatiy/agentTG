"""
Message sender for Telethon userbot.
"""


from telethon import TelegramClient
from telethon.tl.types import Message

from tg_agent.humanizer.delays import TypingDelaySimulator
from tg_agent.logging import get_logger

logger = get_logger(__name__)


class MessageSender:
    """
    Handles sending messages through the userbot.

    Includes human-like delays and typing indicators.
    """

    def __init__(
        self,
        client: TelegramClient,
        typing_simulator: TypingDelaySimulator | None = None,
    ):
        """
        Initialize message sender.

        Args:
            client: Telethon client instance.
            typing_simulator: Optional typing delay simulator.
        """
        self.client = client
        self.typing_simulator = typing_simulator or TypingDelaySimulator()

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to: int | None = None,
        simulate_typing: bool = True,
    ) -> Message | None:
        """
        Send a message to a chat.

        Args:
            chat_id: Target chat ID.
            text: Message text.
            reply_to: Optional message ID to reply to.
            simulate_typing: Whether to simulate typing delay.

        Returns:
            Sent message or None if failed.
        """
        try:
            # Simulate typing if enabled
            if simulate_typing and text:
                await self.typing_simulator.simulate_typing(
                    self.client, chat_id, len(text)
                )

            # Send message
            message = await self.client.send_message(
                entity=chat_id,
                message=text,
                reply_to=reply_to,
                parse_mode=None,  # Plain text, no markdown
            )

            logger.info(f"Sent message to chat {chat_id}")
            return message

        except Exception as e:
            logger.error(f"Failed to send message to chat {chat_id}: {e}")
            return None

    async def send_reply(
        self,
        chat_id: int,
        text: str,
        reply_to_message_id: int,
        simulate_typing: bool = True,
    ) -> Message | None:
        """
        Send a reply to a specific message.

        Args:
            chat_id: Target chat ID.
            text: Reply text.
            reply_to_message_id: Message ID to reply to.
            simulate_typing: Whether to simulate typing delay.

        Returns:
            Sent message or None if failed.
        """
        return await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_to=reply_to_message_id,
            simulate_typing=simulate_typing,
        )

    async def forward_message(
        self,
        from_chat_id: int,
        message_id: int,
        to_chat_id: int,
    ) -> Message | None:
        """
        Forward a message to another chat.

        Args:
            from_chat_id: Source chat ID.
            message_id: Message ID to forward.
            to_chat_id: Destination chat ID.

        Returns:
            Forwarded message or None if failed.
        """
        try:
            message = await self.client.forward_messages(
                entity=to_chat_id,
                messages=message_id,
                from_peer=from_chat_id,
            )

            logger.info(f"Forwarded message {message_id} from {from_chat_id} to {to_chat_id}")
            return message

        except Exception as e:
            logger.error(f"Failed to forward message: {e}")
            return None

    async def edit_message(
        self,
        chat_id: int,
        message_id: int,
        new_text: str,
    ) -> Message | None:
        """
        Edit an existing message.

        Args:
            chat_id: Chat ID.
            message_id: Message ID to edit.
            new_text: New message text.

        Returns:
            Edited message or None if failed.
        """
        try:
            message = await self.client.edit_message(
                entity=chat_id,
                message=message_id,
                text=new_text,
            )

            logger.info(f"Edited message {message_id} in chat {chat_id}")
            return message

        except Exception as e:
            logger.error(f"Failed to edit message: {e}")
            return None

    async def delete_message(
        self,
        chat_id: int,
        message_id: int,
        revoke: bool = True,
    ) -> bool:
        """
        Delete a message.

        Args:
            chat_id: Chat ID.
            message_id: Message ID to delete.
            revoke: Whether to delete for everyone (if possible).

        Returns:
            True if successful.
        """
        try:
            await self.client.delete_messages(
                entity=chat_id,
                message_ids=[message_id],
                revoke=revoke,
            )

            logger.info(f"Deleted message {message_id} in chat {chat_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete message: {e}")
            return False
