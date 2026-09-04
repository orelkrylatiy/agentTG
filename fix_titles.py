import asyncio, os, sqlite3
from telethon import TelegramClient
from dotenv import load_dotenv

load_dotenv()
api_id = int(os.getenv("TG_API_ID"))
api_hash = os.getenv("TG_API_HASH")

async def main():
    client = TelegramClient("data/userbot.session", api_id, api_hash)
    await client.connect()

    conn = sqlite3.connect("data/agent.db")
    rows = conn.execute("SELECT chat_id FROM chat_settings WHERE chat_title IS NULL").fetchall()

    for (chat_id,) in rows:
        try:
            entity = await client.get_entity(chat_id)
            title = getattr(entity, "title", None) or " ".join(filter(None, [
                getattr(entity, "first_name", None),
                getattr(entity, "last_name", None),
            ])) or None
            if title:
                conn.execute("UPDATE chat_settings SET chat_title=? WHERE chat_id=?", (title, chat_id))
                print(f"Updated {chat_id} -> {title}")
            else:
                print(f"No title for {chat_id}")
        except Exception as e:
            print(f"Skip {chat_id}: {e}")

    conn.commit()
    conn.close()
    await client.disconnect()

asyncio.run(main())
