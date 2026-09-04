"""Tests for named reusable Telegram workflows."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_agent.skills.registry import SkillRunner


def make_runner(*, allow_writes=True, outreach_callable=None):
    telegram = MagicMock()
    telegram.unread_chats = AsyncMock(return_value=[])
    telegram.chat_info = AsyncMock(return_value={"chat_id": 1})
    telegram.get_messages = AsyncMock(return_value=[])
    telegram.search_messages = AsyncMock(return_value=[])
    telegram.generate_reply = AsyncMock(
        return_value={
            "ok": True,
            "text": "Черновик",
            "reply_to_message_id": 5,
        }
    )
    telegram.send_message = AsyncMock(return_value={"ok": True, "message_id": 6})
    telegram.scan_channel = AsyncMock(
        return_value={
            "channel_id": -1001,
            "title": "Jobs",
            "username": "jobs",
            "posts": [
                {"message_id": 1, "text": "Frontend @Alice_dev"},
                {"message_id": 2, "text": "Backend https://t.me/Bob_hr"},
            ],
        }
    )
    telegram.configured_channels = AsyncMock(return_value=[])
    return SkillRunner(
        telegram=telegram,
        db=MagicMock(),
        outreach_callable=outreach_callable,
        allow_writes=allow_writes,
    ), telegram


def test_skill_registry_exposes_expected_workflows():
    runner, _ = make_runner()

    names = {skill["name"] for skill in runner.list_skills()}

    assert {
        "unread_inbox",
        "contact_context",
        "telegram_search",
        "channel_research",
        "reply_to_chat",
        "channel_outreach",
        "vacancy_hunt",
        "recent_activity",
    }.issubset(names)


@pytest.mark.asyncio
async def test_channel_research_is_read_only_and_extracts_contacts():
    runner, telegram = make_runner()

    result = await runner.run("channel_research", {"channel": "@jobs", "limit": 5})

    assert result["ok"] is True
    assert result["contacts"] == ["alice_dev", "bob_hr"]
    telegram.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_channel_outreach_defaults_to_dry_run():
    outreach = AsyncMock(return_value=["alice_dev"])
    runner, _ = make_runner(outreach_callable=outreach)

    result = await runner.run("channel_outreach", {"channel": "@jobs"})

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["contacts"] == ["alice_dev", "bob_hr"]
    outreach.assert_not_awaited()


@pytest.mark.asyncio
async def test_reply_skill_does_not_send_when_send_false():
    runner, telegram = make_runner()

    result = await runner.run("reply_to_chat", {"chat": "@alice", "send": False})

    assert result["ok"] is True
    assert result["sent"] is False
    telegram.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_reply_skill_respects_write_kill_switch():
    runner, telegram = make_runner(allow_writes=False)

    result = await runner.run("reply_to_chat", {"chat": "@alice", "send": True})

    assert result["ok"] is False
    assert "disabled" in result["error"]
    telegram.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_channel_outreach_bounded_send_uses_shared_callback():
    outreach = AsyncMock(return_value=["alice_dev"])
    runner, _ = make_runner(outreach_callable=outreach)

    result = await runner.run(
        "channel_outreach",
        {"channel": "@jobs", "send": True, "max_contacts": 1},
    )

    assert result["ok"] is True
    assert result["dry_run"] is False
    assert result["sent_usernames"] == ["alice_dev"]
    outreach.assert_awaited_once()
    assert outreach.await_args.args[3] == 1


@pytest.mark.asyncio
async def test_unknown_skill_returns_available_names():
    runner, _ = make_runner()

    result = await runner.run("does_not_exist")

    assert result["ok"] is False
    assert "unread_inbox" in result["available"]
