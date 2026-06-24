"""
Typing delay simulator for human-like behavior.
"""

import asyncio
import random

from telethon import TelegramClient
from telethon.tl.functions.messages import SetTypingRequest
from telethon.tl.types import SendMessageTypingAction

from tg_agent.logging import get_logger

logger = get_logger(__name__)


class TypingDelaySimulator:
    """
    Simulates human-like typing delays before sending messages.

    Makes agent responses appear more natural by:
    - Showing typing indicator
    - Adding variable delay based on message length
    - Adding random jitter
    """

    def __init__(
        self,
        min_delay_seconds: float = 1.0,
        max_delay_seconds: float = 7.0,
        chars_per_second: int = 15,
        jitter_percent: float = 0.2,
    ):
        """
        Initialize typing delay simulator.

        Args:
            min_delay_seconds: Minimum delay before sending.
            max_delay_seconds: Maximum delay before sending.
            chars_per_second: Simulated typing speed.
            jitter_percent: Random jitter percentage to add.
        """
        self.min_delay = min_delay_seconds
        self.max_delay = max_delay_seconds
        self.chars_per_second = chars_per_second
        self.jitter_percent = jitter_percent

    def calculate_delay(self, message_length: int) -> float:
        """
        Calculate delay based on message length.

        Args:
            message_length: Length of message in characters.

        Returns:
            Delay in seconds.
        """
        # Calculate typing time based on length
        typing_time = message_length / self.chars_per_second

        # Clamp to min/max range
        delay = max(self.min_delay, min(self.max_delay, typing_time))

        # Add random jitter
        jitter = delay * self.jitter_percent * (random.random() * 2 - 1)
        delay += jitter

        return round(delay, 2)

    async def simulate_typing(
        self,
        client: TelegramClient,
        chat_id: int,
        message_length: int,
    ) -> None:
        """
        Simulate typing action before sending.

        Args:
            client: Telethon client.
            chat_id: Target chat ID.
            message_length: Length of message to "type".
        """
        delay = self.calculate_delay(message_length)

        logger.debug(f"Simulating typing for {delay}s (message length: {message_length})")

        try:
            # Send typing action
            await client(
                SetTypingRequest(
                    peer=chat_id,
                    action=SendMessageTypingAction(),
                )
            )

            # Wait for delay
            await asyncio.sleep(delay)

        except Exception as e:
            logger.warning(f"Failed to simulate typing: {e}")
            # Still wait a bit even if typing indicator failed
            await asyncio.sleep(min(1.0, delay))

    async def quick_delay(self) -> None:
        """
        Apply a quick minimal delay.

        Use for short responses or when typing simulation is disabled.
        """
        delay = random.uniform(0.5, 1.5)
        await asyncio.sleep(delay)

    async def long_delay(self) -> None:
        """
        Apply a longer delay for complex responses.
        """
        delay = random.uniform(3.0, 5.0)
        await asyncio.sleep(delay)
