"""Tests for policy module."""

from datetime import datetime, timedelta

import pytest

from tg_agent.policy.filters import MessageFilter
from tg_agent.policy.modes import ChatMode
from tg_agent.storage.models import ChatSettings


class TestMessageFilter:
    @pytest.fixture
    def filter_instance(self):
        return MessageFilter()

    def test_money_pattern_rubles(self, filter_instance):
        assert filter_instance.contains_money_topics("Переведи 500 рублей") is True
        assert filter_instance.contains_money_topics("Стоимость 1000 руб") is True

    def test_money_pattern_dollars(self, filter_instance):
        assert filter_instance.contains_money_topics("Send me $50") is True
        assert filter_instance.contains_money_topics("Price is 100 dollars") is True

    def test_money_pattern_keywords(self, filter_instance):
        assert filter_instance.contains_money_topics("Нужна оплата") is True
        assert filter_instance.contains_money_topics("Какой счет?") is True

    def test_commitment_pattern(self, filter_instance):
        assert filter_instance.contains_commitments("Встретимся завтра") is True
        assert filter_instance.contains_commitments("Созвон в 15:00") is True
        assert filter_instance.contains_commitments("Обещаю помочь") is True

    def test_personal_data_pattern(self, filter_instance):
        assert filter_instance.contains_personal_data("+7 999 123-45-67") is True
        assert filter_instance.contains_personal_data("Мой паспорт") is True

    def test_conflict_pattern(self, filter_instance):
        assert filter_instance.contains_conflict("Это ужасно!") is True
        assert filter_instance.contains_conflict("Какая проблема?") is True

    def test_no_sensitive_topics(self, filter_instance):
        requires_review, reasons = filter_instance.requires_manual_review("Привет, как дела?")
        assert requires_review is False
        assert reasons == []

    def test_is_bot_message(self, filter_instance):
        assert filter_instance.is_bot_message(1500000000, via_bot=True) is True
        assert filter_instance.is_bot_message(123456, via_bot=False) is False

    def test_is_initiative_message(self, filter_instance):
        owner_id = 123456
        assert filter_instance.is_initiative_message(
            sender_id=789012,
            last_message_sender_id=owner_id,
            owner_id=owner_id,
        ) is False
        assert filter_instance.is_initiative_message(
            sender_id=789012,
            last_message_sender_id=999999,
            owner_id=owner_id,
        ) is True


class TestChatMode:
    def test_mode_from_string(self):
        assert ChatMode.from_string("off") == ChatMode.OFF
        assert ChatMode.from_string("WATCH") == ChatMode.WATCH
        assert ChatMode.from_string("Draft") == ChatMode.DRAFT
        assert ChatMode.from_string("AUTO") == ChatMode.AUTO

    def test_mode_from_string_invalid(self):
        with pytest.raises(ValueError):
            ChatMode.from_string("INVALID")

    def test_mode_description(self):
        assert ChatMode.OFF.description == "Agent ignores this chat"
        assert ChatMode.WATCH.description == "Only notify owner, no replies"
        assert ChatMode.DRAFT.description == "Generate drafts for approval"
        assert ChatMode.AUTO.description == "Auto-reply (trusted only)"


class TestPolicyGate:
    @pytest.fixture
    def mock_settings(self):
        class MockSettings:
            agent_global_enabled = True
            owner_telegram_id = 123456
            cooldown_seconds = 120
            owner_takeover_pause_minutes = 30
            require_approval_for_unknown_chats = True
            require_approval_for_initiative_messages = True
            require_approval_for_money_or_commitments = True
            default_chat_mode = "DRAFT"

        return MockSettings()

    @pytest.fixture
    def policy_gate(self, mock_settings):
        from tg_agent.policy.cooldown import CooldownManager
        from tg_agent.policy.gate import PolicyGate

        return PolicyGate(
            settings=mock_settings,
            cooldown_manager=CooldownManager(),
            message_filter=MessageFilter(),
        )

    def test_global_disabled_from_settings(self, mock_settings):
        mock_settings.agent_global_enabled = False
        from tg_agent.policy.cooldown import CooldownManager
        from tg_agent.policy.gate import PolicyGate

        gate = PolicyGate(mock_settings, CooldownManager(), MessageFilter())
        chat_settings = ChatSettings(chat_id=1, mode=ChatMode.AUTO)
        decision = gate.evaluate(chat_settings, sender_id=789, message_text="Hello")
        assert decision.should_process is False
        assert decision.action == "ignore"

    def test_runtime_state_overrides_env(self, policy_gate):
        chat_settings = ChatSettings(chat_id=1, mode=ChatMode.AUTO, is_trusted=True)
        decision = policy_gate.evaluate(
            chat_settings,
            sender_id=789,
            message_text="Hello",
            last_message_sender_id=123456,
            agent_enabled=False,
        )
        assert decision.action == "ignore"
        assert "globally disabled" in decision.reason

    def test_owner_takeover_pause(self, policy_gate):
        chat_settings = ChatSettings(
            chat_id=1,
            mode=ChatMode.AUTO,
            is_trusted=True,
            paused_until=datetime.utcnow() + timedelta(minutes=5),
        )
        decision = policy_gate.evaluate(
            chat_settings,
            sender_id=789,
            message_text="Hello",
            last_message_sender_id=123456,
        )
        assert decision.action == "ignore"
        assert "Owner takeover" in decision.reason

    def test_chat_mode_off(self, policy_gate):
        chat_settings = ChatSettings(chat_id=1, mode=ChatMode.OFF)
        decision = policy_gate.evaluate(chat_settings, sender_id=789, message_text="Hello")
        assert decision.should_process is False
        assert decision.action == "ignore"

    def test_owner_message(self, policy_gate):
        chat_settings = ChatSettings(chat_id=1, mode=ChatMode.AUTO)
        decision = policy_gate.evaluate(
            chat_settings,
            sender_id=123456,
            message_text="Hello",
        )
        assert decision.should_process is False

    def test_watch_mode(self, policy_gate):
        chat_settings = ChatSettings(chat_id=1, mode=ChatMode.WATCH)
        decision = policy_gate.evaluate(chat_settings, sender_id=789, message_text="Hello")
        assert decision.should_process is True
        assert decision.action == "notify"

    def test_draft_mode(self, policy_gate):
        chat_settings = ChatSettings(chat_id=1, mode=ChatMode.DRAFT)
        decision = policy_gate.evaluate(chat_settings, sender_id=789, message_text="Hello")
        assert decision.should_process is True
        assert decision.action == "draft"
        assert decision.requires_approval is True

    def test_auto_mode_not_trusted(self, policy_gate):
        chat_settings = ChatSettings(chat_id=1, mode=ChatMode.AUTO, is_trusted=False)
        decision = policy_gate.evaluate(chat_settings, sender_id=789, message_text="Hello")
        assert decision.should_process is True
        assert decision.action == "draft"

    def test_auto_mode_trusted_safe_message(self, policy_gate):
        chat_settings = ChatSettings(chat_id=1, mode=ChatMode.AUTO, is_trusted=True)
        decision = policy_gate.evaluate(
            chat_settings,
            sender_id=789,
            message_text="Привет, как дела?",
            last_message_sender_id=123456,
        )
        assert decision.should_process is True
        assert decision.action == "auto_reply"

    def test_auto_mode_uses_persisted_cooldown(self, policy_gate):
        chat_settings = ChatSettings(
            chat_id=1,
            mode=ChatMode.AUTO,
            is_trusted=True,
            last_agent_reply_at=datetime.utcnow() - timedelta(seconds=30),
        )
        decision = policy_gate.evaluate(
            chat_settings,
            sender_id=789,
            message_text="ещё вопрос",
            last_message_sender_id=123456,
        )
        assert decision.action == "ignore"
        assert decision.reason == "In cooldown period"

    def test_auto_mode_with_money_topic(self, policy_gate):
        chat_settings = ChatSettings(chat_id=1, mode=ChatMode.AUTO, is_trusted=True)
        decision = policy_gate.evaluate(
            chat_settings,
            sender_id=789,
            message_text="Переведи мне 500 рублей",
        )
        assert decision.should_process is True
        assert decision.action == "draft"
