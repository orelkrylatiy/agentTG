"""
One-shot outreach: fetch last N posts from monitored channel,
extract contacts (@username / phone), generate opening DM, send it.
"""
import asyncio
import re
import sys
import os

sys.path.insert(0, "src")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from tg_agent.config import Settings
from tg_agent.userbot.client import UserbotClient as UserBotClient
from tg_agent.agent.llm import LLMClient

CHANNEL_ID = -1001782596777
N = int(sys.argv[1]) if len(sys.argv) > 1 else 10

OPENING_SYSTEM = """Ты — фронтенд-разработчик с 5 годами опыта, ищешь новую работу.
Пишешь первое сообщение рекрутеру/работодателю из канала вакансий.
Напиши короткое живое сообщение (2-3 предложения) на русском:
— упомяни что видел их вакансию и она тебя заинтересовала
— скажи что ты frontend-разработчик с 5 годами опыта и готов скинуть резюме
— спроси актуальна ли вакансия
Только текст сообщения — без кавычек, заголовков и пояснений."""


def extract_contacts(text: str) -> list[str]:
    """Extract @usernames and phone numbers from post text."""
    contacts = []
    # @usernames
    contacts += re.findall(r'@([a-zA-Z0-9_]{4,32})', text)
    # t.me/username links
    contacts += re.findall(r't\.me/([a-zA-Z0-9_]{4,32})', text)
    return list(dict.fromkeys(contacts))  # deduplicate, preserve order


async def generate_opening(llm: LLMClient, post_text: str) -> str:
    resp = await llm.generate_reply(
        messages=[{"role": "user", "content": f"Вакансия/объявление:\n{post_text[:600]}"}],
        system_prompt=OPENING_SYSTEM,
    )
    return resp.content if resp.success else ""


async def main():
    settings = Settings()
    llm = LLMClient(settings)

    ub = UserBotClient(settings)
    await ub.start()
    client = ub.client  # TelegramClient instance

    print(f"Fetching last {N} posts from channel {CHANNEL_ID}...")
    messages = await client.get_messages(CHANNEL_ID, limit=N)

    sent = 0
    skipped = 0
    for msg in messages:
        text = msg.text or ""
        if not text:
            skipped += 1
            continue

        contacts = extract_contacts(text)
        if not contacts:
            print(f"  [msg {msg.id}] no contacts found, skipping")
            skipped += 1
            continue

        username = contacts[0]
        print(f"\n  [msg {msg.id}] contact: @{username}")
        print(f"  Post snippet: {text[:120].replace(chr(10), ' ')}")

        opening = await generate_opening(llm, text)
        if not opening:
            print(f"  LLM failed to generate opening, skipping")
            skipped += 1
            continue

        print(f"  Opening: {opening}")

        try:
            await client.send_message(username, opening)
            print(f"  ✅ Sent to @{username}")
            sent += 1
        except Exception as e:
            print(f"  ❌ Failed to send to @{username}: {e}")
            skipped += 1

        await asyncio.sleep(10)  # avoid flood limits

    print(f"\nDone. Sent: {sent}, Skipped: {skipped}")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
