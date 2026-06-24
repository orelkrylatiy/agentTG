"""Chat mode helpers built on the storage enum."""

from tg_agent.storage.models import ChatMode as _StorageChatMode


def _description(self: _StorageChatMode) -> str:
    descriptions = {
        _StorageChatMode.OFF: "Agent ignores this chat",
        _StorageChatMode.WATCH: "Only notify owner, no replies",
        _StorageChatMode.DRAFT: "Generate drafts for approval",
        _StorageChatMode.AUTO: "Auto-reply (trusted only)",
    }
    return descriptions.get(self, "Unknown mode")


@classmethod
def _from_string(cls, value: str) -> _StorageChatMode:
    try:
        return cls(value.upper())
    except ValueError as exc:
        raise ValueError(
            f"Invalid mode '{value}'. Must be one of: OFF, WATCH, DRAFT, AUTO"
        ) from exc


_StorageChatMode.description = property(_description)
_StorageChatMode.from_string = _from_string
ChatMode = _StorageChatMode
