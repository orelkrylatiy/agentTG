"""Policy module exports."""

__all__ = ["CooldownManager", "MessageFilter", "PolicyGate", "ChatMode"]


def __getattr__(name: str):
    if name == "CooldownManager":
        from tg_agent.policy.cooldown import CooldownManager

        return CooldownManager
    if name == "MessageFilter":
        from tg_agent.policy.filters import MessageFilter

        return MessageFilter
    if name == "PolicyGate":
        from tg_agent.policy.gate import PolicyGate

        return PolicyGate
    if name == "ChatMode":
        from tg_agent.policy.modes import ChatMode

        return ChatMode
    raise AttributeError(name)
