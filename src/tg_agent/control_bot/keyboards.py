"""
Inline keyboards for control bot.
"""

from dataclasses import dataclass

try:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
except ImportError:  # pragma: no cover
    @dataclass
    class InlineKeyboardButton:
        text: str
        callback_data: str

    @dataclass
    class InlineKeyboardMarkup:
        inline_keyboard: list[list["InlineKeyboardButton"]]


def create_approval_keyboard(action_id: int) -> InlineKeyboardMarkup:
    """
    Create keyboard for approving/rejecting a draft.

    Args:
        action_id: Pending action ID.

    Returns:
        Inline keyboard markup.
    """
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Approve",
                    callback_data=f"approve:{action_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Reject",
                    callback_data=f"reject:{action_id}",
                ),
            ],
        ]
    )
    return keyboard


def create_mode_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """
    Create keyboard for changing chat mode.

    Args:
        chat_id: Chat ID.

    Returns:
        Inline keyboard markup.
    """
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="OFF",
                    callback_data=f"mode:{chat_id}:OFF",
                ),
                InlineKeyboardButton(
                    text="WATCH",
                    callback_data=f"mode:{chat_id}:WATCH",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="DRAFT",
                    callback_data=f"mode:{chat_id}:DRAFT",
                ),
                InlineKeyboardButton(
                    text="AUTO",
                    callback_data=f"mode:{chat_id}:AUTO",
                ),
            ],
        ]
    )
    return keyboard


def create_trust_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """
    Create keyboard for trust toggle.

    Args:
        chat_id: Chat ID.

    Returns:
        Inline keyboard markup.
    """
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔒 Trust",
                    callback_data=f"trust:{chat_id}",
                ),
                InlineKeyboardButton(
                    text="🔓 Untrust",
                    callback_data=f"untrust:{chat_id}",
                ),
            ],
        ]
    )
    return keyboard


def create_chat_action_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """
    Create keyboard for chat actions.

    Args:
        chat_id: Chat ID.

    Returns:
        Inline keyboard markup.
    """
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Change Mode",
                    callback_data=f"change_mode:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔒 Trust/Untrust",
                    callback_data=f"toggle_trust:{chat_id}",
                ),
            ],
        ]
    )
    return keyboard
