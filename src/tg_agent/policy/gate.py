"""
Policy gate - main decision logic for message processing.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from tg_agent.logging import get_logger
from tg_agent.policy.cooldown import CooldownManager
from tg_agent.policy.filters import MessageFilter
from tg_agent.policy.modes import ChatMode
from tg_agent.storage.models import ChatSettings

if TYPE_CHECKING:
    from tg_agent.config import Settings
else:
    Settings = Any

logger = get_logger(__name__)


@dataclass
class PolicyDecision:
    """Result of policy evaluation."""

    should_process: bool
    action: str  # ignore, notify, draft, auto_reply
    reason: str
    requires_approval: bool = False


class PolicyGate:
    """
    Main policy decision engine.

    Evaluates incoming messages and decides:
    - Whether to process them
    - What action to take (ignore, notify, draft, auto-reply)
    - Whether approval is required
    """

    def __init__(
        self,
        settings: Settings,
        cooldown_manager: CooldownManager | None = None,
        message_filter: MessageFilter | None = None,
    ):
        """
        Initialize policy gate.

        Args:
            settings: Application settings.
            cooldown_manager: Cooldown manager instance.
            message_filter: Message filter instance.
        """
        self.settings = settings
        self.cooldown_manager = cooldown_manager or CooldownManager(
            settings.cooldown_seconds
        )
        self.message_filter = message_filter or MessageFilter()
        self.owner_id = settings.owner_telegram_id

    def evaluate(
        self,
        chat_settings: ChatSettings,
        sender_id: int,
        message_text: str,
        is_reply_to_owner: bool = False,
        last_message_sender_id: int | None = None,
    ) -> PolicyDecision:
        """
        Evaluate message and return policy decision.

        Args:
            chat_settings: Chat settings from DB.
            sender_id: Message sender ID.
            message_text: Message text.
            is_reply_to_owner: Whether this is a reply to owner's message.
            last_message_sender_id: ID of last message sender in chat.

        Returns:
            PolicyDecision with action recommendation.
        """
        # Check global enable state
        if not self.settings.agent_global_enabled:
            return PolicyDecision(
                should_process=False,
                action="ignore",
                reason="Agent globally disabled",
            )

        # Check chat mode
        mode = chat_settings.mode
        if mode == ChatMode.OFF:
            return PolicyDecision(
                should_process=False,
                action="ignore",
                reason="Chat mode is OFF",
            )

        # Don't process owner's own messages
        if sender_id == self.owner_id:
            return PolicyDecision(
                should_process=False,
                action="ignore",
                reason="Message from owner",
            )

        # Don't process bot messages
        if self.message_filter.is_bot_message(sender_id):
            return PolicyDecision(
                should_process=False,
                action="ignore",
                reason="Message from bot",
            )

        # Check if this is an initiative message (first in conversation)
        is_initiative = self.message_filter.is_initiative_message(
            sender_id, last_message_sender_id, self.owner_id
        )

        # Check for sensitive topics requiring manual review
        requires_review, review_reasons = self.message_filter.requires_manual_review(
            message_text,
            require_money=self.settings.require_approval_for_money_or_commitments,
            require_commitments=self.settings.require_approval_for_money_or_commitments,
            require_personal=self.settings.require_approval_for_money_or_commitments,
        )

        # Mode-specific logic
        if mode == ChatMode.WATCH:
            return PolicyDecision(
                should_process=True,
                action="notify",
                reason="WATCH mode - notify owner only",
                requires_approval=False,
            )

        if mode == ChatMode.DRAFT:
            # Always require approval in DRAFT mode
            return PolicyDecision(
                should_process=True,
                action="draft",
                reason="DRAFT mode - generate for approval",
                requires_approval=True,
            )

        if mode == ChatMode.AUTO:

            # Check cooldown
            if not self.cooldown_manager.can_reply(chat_settings.chat_id):
                return PolicyDecision(
                    should_process=False,
                    action="ignore",
                    reason="In cooldown period",
                )

            # AUTO = always reply, no gating on sensitive topics or trust
            return PolicyDecision(
                should_process=True,
                action="auto_reply",
                reason="AUTO mode",
                requires_approval=False,
            )

        # Unknown mode - default to draft
        return PolicyDecision(
            should_process=True,
            action="draft",
            reason="Unknown mode - defaulting to draft",
            requires_approval=True,
        )

    def get_pause_until(self) -> datetime:
        """
        Get pause until time after owner activity.

        Returns:
            Datetime until which agent should pause.
        """
        return datetime.utcnow() + timedelta(
            minutes=self.settings.owner_takeover_pause_minutes
        )
