"""
Tests for startup catch-up behavior in the incoming message handler.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from tg_agent.policy.gate import PolicyDecision
from tg_agent.userbot.handlers import IncomingMessageHandler


class _Settings:
    owner_telegram_id = 123456
    cooldown_seconds = 120
    default_chat_mode = "DRAFT"
    control_bot_token = "123456:token"
    max_context_messages = 12
    startup_catchup_enabled = True
    startup_catchup_dialog_limit = 50
    startup_catchup_messages_per_chat = 20
    startup_catchup_auto_reply_max_age_minutes = 15
    prompts_dir = Path(__file__).parent.parent / "prompts"


def _make_handler() -> IncomingMessageHandler:
    return IncomingMessageHandler(
        settings=_Settings(),
        db=MagicMock(),
        client=MagicMock(),
        control_bot=MagicMock(),
        llm_client=MagicMock(),
    )


def test_catchup_keeps_recent_auto_reply() -> None:
    handler = _make_handler()
    decision = PolicyDecision(
        should_process=True,
        action="auto_reply",
        reason="AUTO mode",
        requires_approval=False,
    )
    message = SimpleNamespace(
        date=datetime.now(timezone.utc) - timedelta(minutes=5),
    )

    normalized = handler._normalize_catchup_decision(decision, message)

    assert normalized.action == "auto_reply"
    assert normalized.requires_approval is False


def test_catchup_downgrades_stale_auto_reply() -> None:
    handler = _make_handler()
    decision = PolicyDecision(
        should_process=True,
        action="auto_reply",
        reason="AUTO mode",
        requires_approval=False,
    )
    message = SimpleNamespace(
        date=datetime.now(timezone.utc) - timedelta(hours=2),
    )

    normalized = handler._normalize_catchup_decision(decision, message)

    assert normalized.action == "draft"
    assert normalized.requires_approval is True
    assert "Stale catch-up" in normalized.reason


def test_catchup_downgrades_auto_reply_without_timestamp() -> None:
    handler = _make_handler()
    decision = PolicyDecision(
        should_process=True,
        action="auto_reply",
        reason="AUTO mode",
        requires_approval=False,
    )
    message = SimpleNamespace(date=None)

    normalized = handler._normalize_catchup_decision(decision, message)

    assert normalized.action == "draft"
    assert normalized.requires_approval is True
    assert "without timestamp" in normalized.reason


def test_catchup_keeps_non_auto_decision() -> None:
    handler = _make_handler()
    decision = PolicyDecision(
        should_process=True,
        action="draft",
        reason="Needs approval",
        requires_approval=True,
    )
    message = SimpleNamespace(
        date=datetime.now(timezone.utc) - timedelta(days=1),
    )

    normalized = handler._normalize_catchup_decision(decision, message)

    assert normalized is decision
