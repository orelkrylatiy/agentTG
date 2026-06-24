"""Storage module exports."""

__all__ = [
    "Database",
    "get_db",
    "ChatMode",
    "ChatSettings",
    "GlobalState",
    "MessageLog",
    "MessageDirection",
    "PendingAction",
    "ActionStatus",
    "ChatSettingsRepo",
    "MessageLogRepo",
    "PendingActionRepo",
    "GlobalStateRepo",
]


def __getattr__(name: str):
    if name in {"Database", "get_db"}:
        from tg_agent.storage.db import Database, get_db

        return {"Database": Database, "get_db": get_db}[name]
    if name in {
        "ActionStatus",
        "ChatMode",
        "ChatSettings",
        "GlobalState",
        "MessageDirection",
        "MessageLog",
        "PendingAction",
    }:
        from tg_agent.storage import models

        return getattr(models, name)
    if name in {
        "ChatSettingsRepo",
        "GlobalStateRepo",
        "MessageLogRepo",
        "PendingActionRepo",
    }:
        from tg_agent.storage import repositories

        return getattr(repositories, name)
    raise AttributeError(name)
