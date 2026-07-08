"""
Tests for manual catch-up control bot command.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_agent.control_bot.handlers import cmd_catchup


@pytest.mark.asyncio
async def test_catchup_command_triggers_manual_sync() -> None:
    message = MagicMock()
    message.answer = AsyncMock()

    incoming_handler = MagicMock()
    incoming_handler.catch_up_missed_messages = AsyncMock(return_value=3)

    await cmd_catchup(message, incoming_handler)

    incoming_handler.catch_up_missed_messages.assert_awaited_once_with(force=True)
    assert message.answer.await_count == 2


@pytest.mark.asyncio
async def test_catchup_command_handles_missing_handler() -> None:
    message = MagicMock()
    message.answer = AsyncMock()

    await cmd_catchup(message, None)

    message.answer.assert_awaited_once()
