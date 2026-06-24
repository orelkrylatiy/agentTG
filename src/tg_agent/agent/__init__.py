"""Agent module exports."""

__all__ = ["LLMClient", "PromptManager", "ReplyGenerator"]


def __getattr__(name: str):
    if name == "LLMClient":
        from tg_agent.agent.llm import LLMClient

        return LLMClient
    if name == "PromptManager":
        from tg_agent.agent.prompts import PromptManager

        return PromptManager
    if name == "ReplyGenerator":
        from tg_agent.agent.reply import ReplyGenerator

        return ReplyGenerator
    raise AttributeError(name)
