"""
Minimal LLM smoke test entrypoint.

Run with:
    python -m tg_agent.smoke_llm
"""

import asyncio
import sys

from tg_agent.agent.llm import LLMClient
from tg_agent.config import get_settings
from tg_agent.logging import setup_logging


async def main() -> int:
    try:
        settings = get_settings()
        setup_logging(settings)
        client = LLMClient(settings)
        response = await client.smoke_test()
    except Exception as exc:
        print(f"smoke_test_failed={exc}", file=sys.stderr)
        print(
            "Check CHATGPT_API_BASE, CHATGPT_TOKEN_DIR permissions, and whether your device-code login completed.",
            file=sys.stderr,
        )
        return 1

    print(f"provider={response.provider.value}")
    print(f"model={response.model}")
    print(f"success={response.success}")
    if response.error_message:
        print(f"error={response.error_message}")
    print(f"content={response.content}")

    return 0 if response.success else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
