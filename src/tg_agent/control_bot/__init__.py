"""Control bot module exports."""

__all__ = ["ControlBot", "setup_control_handlers", "HITLManager"]


def __getattr__(name: str):
    if name == "ControlBot":
        from tg_agent.control_bot.bot import ControlBot

        return ControlBot
    if name == "setup_control_handlers":
        from tg_agent.control_bot.handlers import setup_control_handlers

        return setup_control_handlers
    if name == "HITLManager":
        from tg_agent.control_bot.hitl import HITLManager

        return HITLManager
    raise AttributeError(name)
