"""
Reply generation - orchestrates LLM calls for message replies.
"""

from dataclasses import dataclass
from typing import Any

from telethon.tl.types import Message

from tg_agent.agent.llm import LLMClient
from tg_agent.agent.prompts import PromptManager
from tg_agent.agent.sanitizer import clean_reply
from tg_agent.config import Settings
from tg_agent.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GeneratedReply:
    """Result of reply generation."""

    text: str
    success: bool
    error_message: str | None = None
    context_used: int = 0


class ReplyGenerator:
    """
    Generates replies using LLM with context management.
    """

    def __init__(self, settings: Settings, llm_client: LLMClient):
        """
        Initialize reply generator.

        Args:
            settings: Application settings.
            llm_client: LLM client instance.
        """
        self.settings = settings
        self.llm_client = llm_client
        self.prompt_manager = PromptManager(settings)
        self.max_context_messages = settings.max_context_messages

    async def generate(
        self,
        incoming_message: Message,
        context_messages: list[Message] | None = None,
    ) -> GeneratedReply:
        """
        Generate a reply for an incoming message.

        Args:
            incoming_message: The incoming Telethon message.
            context_messages: Optional list of recent messages for context.

        Returns:
            GeneratedReply with text and status.
        """
        # Extract message text
        message_text = incoming_message.text or ""

        if not message_text.strip():
            return GeneratedReply(
                text="",
                success=False,
                error_message="Empty message text",
            )

        # Get sender name
        sender_name = self._get_sender_name(incoming_message)

        # Build context from recent messages as proper user/assistant turns
        context_turns = self._build_context_turns(context_messages or [])

        # Current message always goes last as user role
        if sender_name:
            current = {"role": "user", "content": f"[{sender_name}]: {message_text}"}
        else:
            current = {"role": "user", "content": message_text}

        messages = context_turns + [current]

        # Get system prompt
        system_prompt = self.prompt_manager.get_full_system_prompt()

        # Generate reply
        llm_response = await self.llm_client.generate_reply(
            messages=messages,
            system_prompt=system_prompt,
        )

        if not llm_response.success:
            return GeneratedReply(
                text=llm_response.content,
                success=False,
                error_message=llm_response.error_message,
                context_used=len(context_messages or []),
            )

        dialog_started = bool(context_turns)
        cleaned = clean_reply(llm_response.content, dialog_started, message_text)
        if not cleaned:
            logger.warning(f"Sanitizer emptied reply, using original: {llm_response.content!r}")
            cleaned = llm_response.content
        if cleaned != llm_response.content:
            logger.info(f"Sanitizer: {llm_response.content!r} → {cleaned!r}")

        return GeneratedReply(
            text=cleaned,
            success=True,
            context_used=len(context_messages or []),
        )

    def _get_sender_name(self, message: Message) -> str | None:
        """
        Extract sender name from message.

        Args:
            message: Telethon message.

        Returns:
            Sender name or None.
        """
        if message.sender is None:
            return None

        # Try to get display name
        if hasattr(message.sender, "first_name"):
            first_name = message.sender.first_name or ""
            last_name = getattr(message.sender, "last_name", "") or ""

            if first_name and last_name:
                return f"{first_name} {last_name}"
            elif first_name:
                return first_name
            elif last_name:
                return last_name

        # Try username
        if hasattr(message.sender, "username") and message.sender.username:
            return f"@{message.sender.username}"

        return None

    def _build_context_turns(self, messages: list[Message]) -> list[dict]:
        """Build proper user/assistant turns from recent messages."""
        if not messages:
            return []

        turns = []
        for msg in messages:
            if not msg.text:
                continue
            text = msg.text[:300] + "..." if len(msg.text) > 300 else msg.text
            role = "assistant" if msg.out else "user"
            turns.append({"role": role, "content": text})

        # Merge consecutive same-role messages (LLM APIs require alternating)
        merged: list[dict] = []
        for turn in turns:
            if merged and merged[-1]["role"] == turn["role"]:
                merged[-1]["content"] += "\n" + turn["content"]
            else:
                merged.append(dict(turn))

        # Drop leading assistant messages — LM Studio requires first message to be user
        while merged and merged[0]["role"] == "assistant":
            merged.pop(0)

        return merged

    def _build_context(self, messages: list[Message]) -> str:
        """
        Build context string from recent messages.

        Args:
            messages: List of recent Telethon messages.

        Returns:
            Formatted context string.
        """
        if not messages:
            return ""

        # Take only recent messages up to limit
        recent = messages[-self.max_context_messages :]

        context_lines = []
        for msg in recent:
            if not msg.text:
                continue

            sender = self._get_sender_name(msg) or "Unknown"
            direction = "→" if msg.out else "←"
            text = msg.text[:300] + "..." if len(msg.text) > 300 else msg.text
            context_lines.append(f"{direction} [{sender}]: {text}")

        return "\n".join(context_lines)

    async def generate_summary(
        self,
        message_text: str,
        sender_name: str | None = None,
    ) -> str:
        """
        Generate a brief summary of a message for notification.

        Args:
            message_text: Message text to summarize.
            sender_name: Optional sender name.

        Returns:
            Brief summary text.
        """
        system_prompt = (
            "Кратко суммируй сообщение в 1-2 предложениях. "
            "Укажи суть и любую важную информацию (встречи, деньги, сроки)."
        )

        messages = []
        if sender_name:
            messages.append({
                "role": "user",
                "content": f"[{sender_name}]: {message_text}",
            })
        else:
            messages.append({"role": "user", "content": message_text})

        llm_response = await self.llm_client.generate_reply(
            messages=messages,
            system_prompt=system_prompt,
        )

        if llm_response.success:
            return llm_response.content

        # Fallback - just truncate
        if len(message_text) > 100:
            return message_text[:100] + "..."
        return message_text

    def get_status(self) -> dict[str, Any]:
        """Get generator status."""
        return {
            "max_context_messages": self.max_context_messages,
            "max_reply_chars": self.settings.max_reply_chars,
            "llm_status": self.llm_client.get_status(),
        }
