"""Named Telegram workflows that can be called from MCP or other control planes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from tg_agent.services.telegram import TelegramService
from tg_agent.storage.models import MessageDirection
from tg_agent.storage.repositories import MessageLogRepo

OutreachCallable = Callable[[str, int, int, int | None], Awaitable[list[str]]]


@dataclass(frozen=True)
class SkillSpec:
    """Public metadata for a reusable workflow."""

    name: str
    description: str
    mutates: bool
    examples: tuple[str, ...] = ()


class SkillRunner:
    """Registry and executor for deterministic, reusable Telegram workflows."""

    def __init__(
        self,
        telegram: TelegramService,
        db: Any,
        outreach_callable: OutreachCallable | None = None,
        allow_writes: bool = True,
    ) -> None:
        self.telegram = telegram
        self.db = db
        self.outreach_callable = outreach_callable
        self.allow_writes = allow_writes
        self._specs = {
            "unread_inbox": SkillSpec(
                name="unread_inbox",
                description="Return unread chats with recent message context.",
                mutates=False,
                examples=("run unread_inbox with limit=15",),
            ),
            "contact_context": SkillSpec(
                name="contact_context",
                description="Resolve a person/chat and return metadata plus recent messages.",
                mutates=False,
                examples=("contact_context chat=@username limit=30",),
            ),
            "telegram_search": SkillSpec(
                name="telegram_search",
                description="Search Telegram messages globally or inside one chat.",
                mutates=False,
                examples=("telegram_search query='frontend' limit=30",),
            ),
            "channel_research": SkillSpec(
                name="channel_research",
                description="Read channel posts and extract Telegram contacts from them.",
                mutates=False,
                examples=("channel_research channel=@jobs limit=20",),
            ),
            "reply_to_chat": SkillSpec(
                name="reply_to_chat",
                description="Generate a contextual reply; optionally send it.",
                mutates=True,
                examples=("reply_to_chat chat=@name send=false",),
            ),
            "channel_outreach": SkillSpec(
                name="channel_outreach",
                description=(
                    "Scan a channel, find contacts and optionally run configured LLM "
                    "outreach. Defaults to dry-run."
                ),
                mutates=True,
                examples=("channel_outreach channel=@jobs limit=10 send=false",),
            ),
            "vacancy_hunt": SkillSpec(
                name="vacancy_hunt",
                description=(
                    "Research all configured channels and optionally contact people "
                    "from matching posts. Defaults to research-only."
                ),
                mutates=True,
                examples=("vacancy_hunt limit_per_channel=10 send=false",),
            ),
            "recent_activity": SkillSpec(
                name="recent_activity",
                description="Return recent audited agent message activity.",
                mutates=False,
                examples=("recent_activity limit=30",),
            ),
        }

    def list_skills(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "mutates": spec.mutates,
                "examples": list(spec.examples),
            }
            for spec in self._specs.values()
        ]

    async def run(self, name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        if name not in self._specs:
            return {
                "ok": False,
                "error": f"unknown skill: {name}",
                "available": sorted(self._specs),
            }

        handlers = {
            "unread_inbox": self._unread_inbox,
            "contact_context": self._contact_context,
            "telegram_search": self._telegram_search,
            "channel_research": self._channel_research,
            "reply_to_chat": self._reply_to_chat,
            "channel_outreach": self._channel_outreach,
            "vacancy_hunt": self._vacancy_hunt,
            "recent_activity": self._recent_activity,
        }
        try:
            result = await handlers[name](params)
        except (TypeError, ValueError) as exc:
            return {"skill": name, "ok": False, "error": str(exc)}
        return {"skill": name, **result}

    async def _unread_inbox(self, params: dict[str, Any]) -> dict[str, Any]:
        chats = await self.telegram.unread_chats(
            limit=int(params.get("limit", 20)),
            messages_per_chat=int(params.get("messages_per_chat", 5)),
        )
        return {"ok": True, "count": len(chats), "chats": chats}

    async def _contact_context(self, params: dict[str, Any]) -> dict[str, Any]:
        chat = self._required(params, "chat")
        info = await self.telegram.chat_info(chat)
        messages = await self.telegram.get_messages(
            chat,
            limit=int(params.get("limit", 30)),
        )
        return {"ok": True, "chat": info, "messages": messages}

    async def _telegram_search(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(self._required(params, "query"))
        chat = params.get("chat")
        messages = await self.telegram.search_messages(
            query=query,
            chat=chat,
            limit=int(params.get("limit", 30)),
        )
        return {"ok": True, "query": query, "count": len(messages), "messages": messages}

    async def _channel_research(self, params: dict[str, Any]) -> dict[str, Any]:
        channel = self._required(params, "channel")
        data = await self.telegram.scan_channel(
            channel=channel,
            limit=int(params.get("limit", 20)),
            keyword=params.get("keyword"),
        )
        contacts = self._contacts_from_posts(data["posts"])
        return {**data, "ok": True, "contacts": contacts}

    async def _reply_to_chat(self, params: dict[str, Any]) -> dict[str, Any]:
        chat = self._required(params, "chat")
        generated = await self.telegram.generate_reply(
            chat,
            context_limit=int(params.get("context_limit", 12)),
        )
        if not generated.get("ok") or not bool(params.get("send", False)):
            return {"ok": bool(generated.get("ok")), "draft": generated, "sent": False}

        if not self.allow_writes:
            return {
                "ok": False,
                "error": "MCP/skill writes are disabled",
                "draft": generated,
                "sent": False,
            }

        sent = await self.telegram.send_message(
            chat=chat,
            text=str(generated["text"]),
            reply_to=generated.get("reply_to_message_id"),
            simulate_typing=bool(params.get("simulate_typing", True)),
        )
        return {"ok": bool(sent.get("ok")), "draft": generated, "sent": sent}

    async def _channel_outreach(self, params: dict[str, Any]) -> dict[str, Any]:
        channel = self._required(params, "channel")
        research = await self.telegram.scan_channel(
            channel=channel,
            limit=int(params.get("limit", 10)),
            keyword=params.get("keyword"),
        )
        contacts = self._contacts_from_posts(research["posts"])
        send = bool(params.get("send", False))
        max_contacts = max(0, min(int(params.get("max_contacts", 5)), 25))

        if not send:
            return {
                **research,
                "ok": True,
                "dry_run": True,
                "contacts": contacts[:max_contacts],
            }
        if not self.allow_writes:
            return {
                **research,
                "ok": False,
                "error": "MCP/skill writes are disabled",
                "dry_run": True,
                "contacts": contacts[:max_contacts],
            }
        if self.outreach_callable is None:
            return {
                **research,
                "ok": False,
                "error": "outreach service is unavailable",
                "dry_run": True,
                "contacts": contacts[:max_contacts],
            }

        remaining = max_contacts
        sent_usernames: list[str] = []
        for post in research["posts"]:
            if remaining <= 0:
                break
            post_contacts = self.telegram.extract_contacts(post.get("text") or "")
            if not post_contacts:
                continue
            sent = await self.outreach_callable(
                post.get("text") or "",
                int(research["channel_id"]),
                int(params.get("max_per_hour", 60)),
                remaining,
            )
            sent_usernames.extend(sent)
            remaining -= len(sent)

        return {
            **research,
            "ok": True,
            "dry_run": False,
            "contacts": contacts[:max_contacts],
            "sent_usernames": list(dict.fromkeys(sent_usernames)),
        }

    async def _vacancy_hunt(self, params: dict[str, Any]) -> dict[str, Any]:
        configured = await self.telegram.configured_channels()
        limit = int(params.get("limit_per_channel", 10))
        send = bool(params.get("send", False))
        remaining = max(0, min(int(params.get("max_contacts", 10)), 50))

        channels: list[dict[str, Any]] = []
        total_contacts = 0
        sent_usernames: list[str] = []
        for channel in configured:
            data = await self.telegram.scan_channel(
                channel=channel["channel_id"],
                limit=limit,
                keyword=params.get("keyword"),
            )
            contacts = self._contacts_from_posts(data["posts"])
            channels.append(
                {
                    **data,
                    "configured_auto_outreach": channel["auto_outreach"],
                    "configured_keywords": channel["keywords"],
                    "contacts": contacts,
                }
            )
            total_contacts += len(contacts)

            if (
                send
                and remaining > 0
                and self.allow_writes
                and channel["auto_outreach"]
                and self.outreach_callable is not None
            ):
                for post in data["posts"]:
                    if remaining <= 0:
                        break
                    post_contacts = self.telegram.extract_contacts(post.get("text") or "")
                    if not post_contacts:
                        continue
                    sent = await self.outreach_callable(
                        post.get("text") or "",
                        int(channel["channel_id"]),
                        int(channel["max_per_hour"]),
                        remaining,
                    )
                    sent_usernames.extend(sent)
                    remaining -= len(sent)

        return {
            "ok": not send or self.allow_writes,
            "dry_run": not send,
            "channels": channels,
            "channel_count": len(channels),
            "contacts_found": total_contacts,
            "sent_usernames": list(dict.fromkeys(sent_usernames)),
            "writes_allowed": self.allow_writes,
        }

    async def _recent_activity(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = max(1, min(int(params.get("limit", 30)), 100))
        chat_id = int(params.get("chat_id", 0) or 0)
        with self.db.get_sync_session() as session:
            logs = MessageLogRepo(session).get_recent(chat_id=chat_id, limit=limit)

        return {
            "ok": True,
            "activity": [
                {
                    "chat_id": log.chat_id,
                    "message_id": log.message_id,
                    "sender_id": log.sender_id,
                    "direction": (
                        log.direction.value
                        if isinstance(log.direction, MessageDirection)
                        else str(log.direction)
                    ),
                    "text": log.text,
                    "created_at": log.created_at.isoformat(),
                }
                for log in logs
            ],
        }

    @staticmethod
    def _contacts_from_posts(posts: list[dict[str, Any]]) -> list[str]:
        contacts: list[str] = []
        for post in posts:
            contacts.extend(TelegramService.extract_contacts(post.get("text") or ""))
        return list(dict.fromkeys(contacts))

    @staticmethod
    def _required(params: dict[str, Any], key: str) -> Any:
        value = params.get(key)
        if value is None or value == "":
            raise ValueError(f"missing required skill parameter: {key}")
        return value
