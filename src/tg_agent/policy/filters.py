"""
Message filters for policy decisions.
"""

import re

from tg_agent.logging import get_logger

logger = get_logger(__name__)


class MessageFilter:
    """
    Filters messages for safety and policy compliance.
    """

    # Patterns that indicate money/financial topics
    MONEY_PATTERNS = [
        r"\d+\s*(руб|рублей|доллар|долларов|евро|usd|eur|\$|€)",
        r"\d+\s*(dollar|dollars|euro|euros)",
        r"\$\d+",
        r"€\d+",
        r"\d+\s*тыс",
        r"\d+\s*млн",
        r"\d+\s*млрд",
        r"(перевод|оплата|платеж|счет|деньги|зарплата|цена|стоимость)",
    ]

    # Patterns indicating commitments/meetings
    COMMITMENT_PATTERNS = [
        r"(встретимся|встреча|свидание|совещание|звонок|созвон)",
        r"(завтра|сегодня|в\s+\d+:\d+|в\s+\d+\s*часов?)",
        r"(обещаю|гарантирую|договорились|ок|договор)",
    ]

    # Patterns indicating personal data
    PERSONAL_DATA_PATTERNS = [
        r"\+?\d[\d\s-]{8,}\d",  # Phone numbers
        r"\b\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\b",  # Card numbers
        r"(паспорт|прописка|адрес|снилс|инн)",
    ]

    # Patterns indicating conflict
    CONFLICT_PATTERNS = [
        r"(почему|как так|неправильно|ошибка|проблема|жалоба|скандал)",
        r"(ужасно|отвратительно|безобразие|позор)",
    ]

    def __init__(self):
        self.money_regex = [re.compile(p, re.IGNORECASE) for p in self.MONEY_PATTERNS]
        self.commitment_regex = [re.compile(p, re.IGNORECASE) for p in self.COMMITMENT_PATTERNS]
        self.personal_data_regex = [
            re.compile(p, re.IGNORECASE) for p in self.PERSONAL_DATA_PATTERNS
        ]
        self.conflict_regex = [re.compile(p, re.IGNORECASE) for p in self.CONFLICT_PATTERNS]

    def contains_money_topics(self, text: str) -> bool:
        """Check if message contains money/financial topics."""
        return any(regex.search(text) for regex in self.money_regex)

    def contains_commitments(self, text: str) -> bool:
        """Check if message contains commitment/meeting topics."""
        return any(regex.search(text) for regex in self.commitment_regex)

    def contains_personal_data(self, text: str) -> bool:
        """Check if message contains personal data."""
        return any(regex.search(text) for regex in self.personal_data_regex)

    def contains_conflict(self, text: str) -> bool:
        """Check if message indicates conflict/complaint."""
        return any(regex.search(text) for regex in self.conflict_regex)

    def requires_manual_review(
        self,
        text: str,
        require_money: bool = True,
        require_commitments: bool = True,
        require_personal: bool = True,
    ) -> tuple[bool, list[str]]:
        """
        Check if message requires manual review.

        Returns:
            Tuple of (requires_review, list of reasons).
        """
        reasons = []

        if require_money and self.contains_money_topics(text):
            reasons.append("money_topics")

        if require_commitments and self.contains_commitments(text):
            reasons.append("commitments")

        if require_personal and self.contains_personal_data(text):
            reasons.append("personal_data")

        if self.contains_conflict(text):
            reasons.append("conflict")

        return len(reasons) > 0, reasons

    def is_bot_message(self, sender_id: int | None, via_bot: bool = False) -> bool:
        """Check if message is from a bot (only via_bot flag is reliable)."""
        return via_bot

    def is_initiative_message(
        self,
        sender_id: int,
        last_message_sender_id: int | None,
        owner_id: int,
    ) -> bool:
        """
        Check if this is an initiative message (first in conversation).

        An initiative message is when someone writes to the owner
        and the last message was not from the owner.
        """
        # If last message was from owner, this is a reply, not initiative
        if last_message_sender_id == owner_id:
            return False

        # If this is the first message we see, treat as initiative
        if last_message_sender_id is None:
            return True

        # If sender is not owner and last was not owner, it's initiative
        return sender_id != owner_id
