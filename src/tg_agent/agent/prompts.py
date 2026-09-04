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
    """Load global and chat/channel-specific prompt layers from disk."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.prompts_dir = settings.prompts_dir
        self.outreach_prompts_dir = self.prompts_dir / "outreach"
        self.reply_prompts_dir = self.prompts_dir / "reply"

    def _load_prompt_file(self, filename: str) -> str:
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
        """Reload on every use so edits apply without process restart."""
        prompt = self._load_prompt_file("system.ru.txt")
        return prompt or "Отвечай кратко и естественно, как в обычной переписке в Telegram."

    @property
    def safety_prompt(self) -> str:
        """Reload on every use, matching system/persona hot-reload semantics."""
        prompt = self._load_prompt_file("safety.ru.txt")
        if prompt:
            return prompt
        logger.warning("Using default safety prompt")
        return (
            "Не выдумывай факты, договорённости, деньги, даты или личные данные. "
            "Пиши только содержательную часть ответа; решение об отправке принимает policy engine."
        )

    @property
    def persona(self) -> str:
        """Reload on every use so persona edits apply without restart."""
        return self._load_prompt_file("persona.ru.txt")

    def get_full_system_prompt(self) -> str:
        parts = [self.system_prompt]
        if persona := self.persona:
            parts.append(persona)
        if safety := self.safety_prompt:
            parts.append(safety)
        return "\n\n".join(parts)

    def get_reply_system_prompt(self, chat_id: int) -> str:
        """Compose invariant global layers plus optional chat-specific behavior."""
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
        messages = [
            {
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            }
            for msg in chat_history
        ]
        if sender_name:
            messages.append({"role": "user", "content": f"[{sender_name}]: {current_message}"})
        else:
            messages.append({"role": "user", "content": current_message})
        return messages

    def create_reply_request(
        self,
        chat_context: str,
        incoming_message: str,
        sender_name: str | None = None,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if chat_context:
            messages.append({"role": "user", "content": f"Контекст переписки:\n{chat_context}"})
        if sender_name:
            messages.append({"role": "user", "content": f"[{sender_name}]: {incoming_message}"})
        else:
            messages.append({"role": "user", "content": incoming_message})
        return messages

    def get_outreach_prompt(self, channel_id: int) -> str:
        custom_path = self.outreach_prompts_dir / f"{channel_id}.txt"
        default_path = self.outreach_prompts_dir / "default.txt"

        if content := self._load_custom_prompt(
            custom_path,
            f"custom outreach prompt for channel {channel_id}",
        ):
            return content
        if content := self._load_custom_prompt(default_path, "default outreach prompt"):
            return content

        return """Ты — фронтенд-разработчик с 5 годами опыта, ищешь новую работу.
Напиши короткое сообщение (2-3 предложения) рекрутеру.
Упомяни деталь из вакансии, скажи что готов скинуть резюме, спроси актуальна ли позиция."""

    def get_reply_prompt(self, chat_id: int) -> str:
        custom_path = self.reply_prompts_dir / f"{chat_id}.txt"
        default_path = self.reply_prompts_dir / "default.txt"

        if content := self._load_custom_prompt(
            custom_path,
            f"custom reply prompt for chat {chat_id}",
        ):
            return content
        if content := self._load_custom_prompt(default_path, "default reply prompt"):
            return content

        return """Ты отвечаешь в Telegram от имени Максима — живого человека.
Пиши кратко (1-2 фразы), по-русски, неформально.
Без markdown, без приветствий если диалог уже идёт."""

    def _load_custom_prompt(self, path: Path, label: str) -> str:
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
