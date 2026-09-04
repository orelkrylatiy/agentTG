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

    The gate is intentionally deterministic. The LLM generates text; it never
    decides whether a message may be sent automatically.
    """

    def __init__(
        self,
        settings: Settings,
        cooldown_manager: CooldownManager | None = None,
        message_filter: MessageFilter | None = None,
    ):
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
        agent_enabled: bool | None = None,
    ) -> PolicyDecision:
        """Evaluate an incoming message and return a deterministic action."""
        # Runtime state in SQLite is the source of truth. The env value is only
        # a bootstrap default and remains the fallback for tests/standalone use.
        enabled = (
            self.settings.agent_global_enabled
            if agent_enabled is None
            else agent_enabled
        )
        if not enabled:
            return PolicyDecision(
                should_process=False,
                action="ignore",
                reason="Agent globally disabled",
            )

        # Owner takeover: if the owner has recently interacted manually in this
        # chat, keep the automation out until the pause expires.
        if (
            chat_settings.paused_until is not None
            and datetime.utcnow() < chat_settings.paused_until
        ):
            return PolicyDecision(
                should_process=False,
                action="ignore",
                reason=f"Owner takeover until {chat_settings.paused_until.isoformat()}",
            )

        mode = chat_settings.mode
        if mode == ChatMode.OFF:
            return PolicyDecision(
                should_process=False,
                action="ignore",
                reason="Chat mode is OFF",
            )

        if sender_id == self.owner_id:
            return PolicyDecision(
                should_process=False,
                action="ignore",
                reason="Message from owner",
            )

        if self.message_filter.is_bot_message(sender_id):
            return PolicyDecision(
                should_process=False,
                action="ignore",
                reason="Message from bot",
            )

        is_initiative = self.message_filter.is_initiative_message(
            sender_id, last_message_sender_id, self.owner_id
        )

        requires_review, review_reasons = self.message_filter.requires_manual_review(
            message_text,
            require_money=self.settings.require_approval_for_money_or_commitments,
            require_commitments=self.settings.require_approval_for_money_or_commitments,
            require_personal=self.settings.require_approval_for_money_or_commitments,
        )

        if mode == ChatMode.WATCH:
            return PolicyDecision(
                should_process=True,
                action="notify",
                reason="WATCH mode - notify owner only",
                requires_approval=False,
            )

        if mode == ChatMode.DRAFT:
            return PolicyDecision(
                should_process=True,
                action="draft",
                reason="DRAFT mode - generate for approval",
                requires_approval=True,
            )

        if mode == ChatMode.AUTO:
            if not self.cooldown_manager.can_reply(
                chat_settings.chat_id,
                last_reply_at=chat_settings.last_agent_reply_at,
            ):
                return PolicyDecision(
                    should_process=False,
                    action="ignore",
                    reason="In cooldown period",
                )

            if (
                self.settings.require_approval_for_unknown_chats
                and not chat_settings.is_trusted
            ):
                return PolicyDecision(
                    should_process=True,
                    action="draft",
                    reason="AUTO mode requires trusted chat",
                    requires_approval=True,
                )

            if (
                self.settings.require_approval_for_initiative_messages
                and is_initiative
            ):
                return PolicyDecision(
                    should_process=True,
                    action="draft",
                    reason="Initiative message requires approval",
                    requires_approval=True,
                )

            if requires_review:
                return PolicyDecision(
                    should_process=True,
                    action="draft",
                    reason=(
                        "Sensitive topic requires approval: "
                        + ", ".join(review_reasons)
                    ),
                    requires_approval=True,
                )

            return PolicyDecision(
                should_process=True,
                action="auto_reply",
                reason="AUTO mode",
                requires_approval=False,
            )

        return PolicyDecision(
            should_process=True,
            action="draft",
            reason="Unknown mode - defaulting to draft",
            requires_approval=True,
        )

    def get_pause_until(self) -> datetime:
        """Return the owner-takeover pause deadline for a manual owner action."""
        return datetime.utcnow() + timedelta(
            minutes=self.settings.owner_takeover_pause_minutes
        )
