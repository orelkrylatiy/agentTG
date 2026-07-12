"""
Prompt management - loading and formatting prompts.

Supports custom prompts per channel (outreach) and per chat (reply) with fallback to defaults.
See: prompts/PROMPTS_SPEC.md for full specification.
"""


from pathlib import Path

from tg_agent.config import Settings
from tg_agent.logging import get_logger

logger = get_logger(__name__)


class PromptManager:
    """
    Manages loading and formatting of prompts.

    Supports:
    - System prompts (legacy): system.ru.txt, safety.ru.txt
    - Outreach prompts: prompts/outreach/{channel_id}.txt → default.txt
    - Reply prompts: prompts/reply/{chat_id}.txt → default.txt
    """

    def __init__(self, settings: Settings):
        """
        Initialize prompt manager.

        Args:
            settings: Application settings.
        """
        self.settings = settings
        self.prompts_dir = settings.prompts_dir
        self._system_prompt: str | None = None
        self._safety_prompt: str | None = None

        # Prompt directories for outreach and reply
        self.outreach_prompts_dir = self.prompts_dir / "outreach"
        self.reply_prompts_dir = self.prompts_dir / "reply"

    def _load_prompt_file(self, filename: str) -> str:
        """
        Load prompt from file.

        Args:
            filename: Name of the prompt file.

        Returns:
            Prompt text content.
        """
        filepath = self.prompts_dir / filename

        if not filepath.exists():
            logger.warning(f"Prompt file not found: {filepath}")
            return ""

        try:
            content = filepath.read_text(encoding="utf-8").strip()
            logger.debug(f"Loaded prompt from {filepath}")
            return content
        except Exception as e:
            logger.error(f"Error loading prompt {filepath}: {e}")
            return ""

    @property
    def system_prompt(self) -> str:
        """Always reload from file so edits take effect without restart."""
        prompt = self._load_prompt_file("system.ru.txt")
        if not prompt:
            return "Отвечай кратко и естественно, как в обычной переписке в Telegram."
        return prompt

    @property
    def safety_prompt(self) -> str:
        """Get safety prompt, loading if necessary."""
        if self._safety_prompt is None:
            self._safety_prompt = self._load_prompt_file("safety.ru.txt")

            if not self._safety_prompt:
                # Fallback default
                self._safety_prompt = (
                    "Не обещай встречи, деньги или обязательства без подтверждения владельца. "
                    "Если не уверен — попроси владельца проверить ответ."
                )
                logger.warning("Using default safety prompt")

        return self._safety_prompt

    @property
    def persona(self) -> str:
        """Always reload persona from file so edits take effect without restart."""
        return self._load_prompt_file("persona.ru.txt")

    def get_full_system_prompt(self) -> str:
        """Get combined system + persona + safety prompt."""
        parts = [self.system_prompt]
        if persona := self.persona:
            parts.append(persona)
        if safety := self.safety_prompt:
            parts.append(safety)
        return "\n\n".join(parts)

    def get_reply_system_prompt(self, chat_id: int) -> str:
        """
        Get reply system prompt with global policy layers preserved.

        Chat-specific and default reply prompts customize behavior, but they do not
        replace the invariant system/persona/safety instructions.
        """
        parts = [self.get_full_system_prompt()]
        if reply_prompt := self.get_reply_prompt(chat_id):
            parts.append(reply_prompt)
        return "\n\n".join(parts)

    def format_context_messages(
        self,
        chat_history: list[dict[str, str]],
        current_message: str,
        sender_name: str | None = None,
    ) -> list[dict[str, str]]:
        """
        Format context messages for LLM.

        Args:
            chat_history: List of previous messages.
            current_message: Current incoming message.
            sender_name: Optional sender name.

        Returns:
            Formatted message list for LLM.
        """
        messages = []

        # Add chat history
        for msg in chat_history:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        # Add current message
        if sender_name:
            messages.append({
                "role": "user",
                "content": f"[{sender_name}]: {current_message}",
            })
        else:
            messages.append({
                "role": "user",
                "content": current_message,
            })

        return messages

    def create_reply_request(
        self,
        chat_context: str,
        incoming_message: str,
        sender_name: str | None = None,
    ) -> list[dict[str, str]]:
        """
        Create a full request for reply generation.

        Args:
            chat_context: Recent chat context.
            incoming_message: Current message to reply to.
            sender_name: Optional sender name.

        Returns:
            Message list ready for LLM.
        """
        messages = []

        # Add context if available
        if chat_context:
            messages.append({
                "role": "user",
                "content": f"Контекст переписки:\n{chat_context}",
            })

        # Add current message
        if sender_name:
            messages.append({
                "role": "user",
                "content": f"[{sender_name}]: {incoming_message}",
            })
        else:
            messages.append({
                "role": "user",
                "content": incoming_message,
            })

        return messages

    def get_outreach_prompt(self, channel_id: int) -> str:
        """
        Load outreach prompt for a specific channel.

        Tries to load custom prompt for channel, falls back to default.

        Args:
            channel_id: Telegram channel ID (e.g., -1001782596777)

        Returns:
            Prompt text for outreach messages.
        """
        custom_path = self.outreach_prompts_dir / f"{channel_id}.txt"
        default_path = self.outreach_prompts_dir / "default.txt"

        if content := self._load_custom_prompt(
            custom_path,
            f"custom outreach prompt for channel {channel_id}",
        ):
            return content
        if content := self._load_custom_prompt(default_path, "default outreach prompt"):
            return content

        # Last resort: hardcoded fallback
        return """Ты — фронтенд-разработчик с 5 годами опыта, ищешь новую работу.
Напиши короткое сообщение (2-3 предложения) рекрутеру.
Упомяни деталь из вакансии, скажи что готов скинуть резюме, спроси актуальна ли позиция."""

    def get_reply_prompt(self, chat_id: int) -> str:
        """
        Load reply prompt for a specific chat.

        Tries to load custom prompt for chat, falls back to default.

        Args:
            chat_id: Telegram chat ID (e.g., 8465750445)

        Returns:
            Prompt text for reply generation.
        """
        custom_path = self.reply_prompts_dir / f"{chat_id}.txt"
        default_path = self.reply_prompts_dir / "default.txt"

        if content := self._load_custom_prompt(
            custom_path,
            f"custom reply prompt for chat {chat_id}",
        ):
            return content
        if content := self._load_custom_prompt(default_path, "default reply prompt"):
            return content

        # Last resort: hardcoded fallback
        return """Ты отвечаешь в Telegram от имени Максима — живого человека.
Пиши кратко (1-2 фразы), по-русски, неформально.
Без markdown, без приветствий если диалог уже идёт."""

    def _load_custom_prompt(self, path: Path, label: str) -> str:
        """
        Load a custom/default prompt file.

        Empty files are treated as missing so fallback resolution can continue.
        """
        if not path.exists():
            return ""

        try:
            content = path.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.warning(f"Error reading {label} {path}: {e}")
            return ""

        if not content:
            logger.warning(f"Ignoring empty {label}: {path}")
            return ""

        logger.info(f"Loaded {label}")
        return content
