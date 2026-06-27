"""
Prompt management - loading and formatting prompts.
"""


from tg_agent.config import Settings
from tg_agent.logging import get_logger

logger = get_logger(__name__)


class PromptManager:
    """
    Manages loading and formatting of prompts.
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
