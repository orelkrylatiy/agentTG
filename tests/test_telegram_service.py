"""Tests for the reusable Telegram application service."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_agent.services.telegram import TelegramService
from tg_agent.storage.db import Database
from tg_agent.storage.models import MessageDirection
from tg_agent.storage.repositories import MessageLogRepo


def make_service(client, db=None):
    settings = SimpleNamespace(
        max_context_messages=12,
        max_reply_chars=800,
        owner_telegram_id=123456,
    )
    return TelegramService(
        settings=settings,
        client=client,
        db=db or MagicMock(),
        llm_client=MagicMock(),
        prompt_manager=MagicMock(),
    )


@pytest.mark.asyncio
async def test_list_dialogs_can_filter_unread():
    client = MagicMock()
    client.get_dialogs = AsyncMock(
        return_value=[
            SimpleNamespace(
                id=1,
                name="Unread",
                entity=SimpleNamespace(username="alice"),
                unread_count=2,
                unread_mentions_count=1,
                pinned=False,
                is_user=True,
                is_group=False,
                is_channel=False,
                message=SimpleNamespace(id=10, date=datetime(2026, 9, 4, 8, 0)),
            ),
            SimpleNamespace(
                id=2,
                name="Read",
                entity=SimpleNamespace(username="bob"),
                unread_count=0,
                unread_mentions_count=0,
                pinned=False,
                is_user=True,
                is_group=False,
                is_channel=False,
                message=SimpleNamespace(id=20, date=datetime(2026, 9, 4, 9, 0)),
            ),
        ]
    )
    service = make_service(client)

    dialogs = await service.list_dialogs(limit=20, unread_only=True)

    assert [dialog["chat_id"] for dialog in dialogs] == [1]
    assert dialogs[0]["username"] == "alice"
    assert dialogs[0]["unread_count"] == 2


@pytest.mark.asyncio
async def test_unread_chats_includes_message_context():
    client = MagicMock()
    service = make_service(client)
    service.list_dialogs = AsyncMock(
        return_value=[{"chat_id": 42, "name": "Alice", "unread_count": 3}]
    )
    service.get_messages = AsyncMock(
        return_value=[{"message_id": 5, "text": "Привет"}]
    )

    result = await service.unread_chats(limit=10, messages_per_chat=4)

    assert result[0]["chat_id"] == 42
    assert result[0]["messages"][0]["text"] == "Привет"
    service.get_messages.assert_awaited_once_with(42, limit=4)


def test_extract_contacts_deduplicates_and_normalizes():
    text = "Пишите @Alice_dev или https://t.me/alice_dev, ещё @Bob_hr"

    assert TelegramService.extract_contacts(text) == ["alice_dev", "bob_hr"]


@pytest.mark.asyncio
async def test_generate_reply_uses_latest_incoming_and_older_context():
    client = MagicMock()
    incoming = SimpleNamespace(
        id=30,
        chat_id=7,
        text="Есть время созвониться?",
        out=False,
        sender=None,
    )
    newest_outgoing = SimpleNamespace(
        id=31,
        chat_id=7,
        text="later outgoing",
        out=True,
        sender=None,
    )
    older_incoming = SimpleNamespace(
        id=20,
        chat_id=7,
        text="Старая реплика",
        out=False,
        sender=None,
    )
    client.get_messages = AsyncMock(
        return_value=[newest_outgoing, incoming, older_incoming]
    )
    service = make_service(client)
    service.reply_generator.generate = AsyncMock(
        return_value=SimpleNamespace(
            success=True,
            text="Да, могу вечером",
            error_message=None,
            context_used=1,
        )
    )

    result = await service.generate_reply(chat="@alice", context_limit=10)

    assert result["ok"] is True
    assert result["reply_to_message_id"] == 30
    call = service.reply_generator.generate.await_args
    assert call.kwargs["incoming_message"] is incoming
    assert call.kwargs["context_messages"] == [older_incoming]


@pytest.mark.asyncio
async def test_send_message_writes_audit_log(tmp_path):
    db = Database(database_url=f"sqlite:///{tmp_path / 'agent.db'}")
    await db.init_db()

    client = MagicMock()
    client.get_entity = AsyncMock(
        return_value=SimpleNamespace(first_name="Alice", last_name=None, username="alice")
    )
    client.get_peer_id = AsyncMock(return_value=777)
    service = make_service(client, db=db)
    service.sender.send_message = AsyncMock(return_value=SimpleNamespace(id=991))

    result = await service.send_message(
        chat="@alice",
        text="Привет",
        simulate_typing=False,
    )

    assert result == {
        "ok": True,
        "chat_id": 777,
        "message_id": 991,
        "text": "Привет",
    }
    with db.get_sync_session() as session:
        logs = MessageLogRepo(session).get_recent(chat_id=777, limit=10)
    assert len(logs) == 1
    assert logs[0].direction == MessageDirection.AGENT_SENT
    assert logs[0].text == "Привет"
