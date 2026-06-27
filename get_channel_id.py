import asyncio, os
from telethon import TelegramClient
from dotenv import load_dotenv

load_dotenv()
api_id = int(os.getenv("TG_API_ID"))
api_hash = os.getenv("TG_API_HASH")

async def main():
    client = TelegramClient("data/userbot.session", api_id, api_hash)
    await client.connect()
    try:
        entity = await client.get_entity("https://t.me/+ucoAOCsXCwk3ZmFi")
        print(f"ID: {entity.id}")
        print(f"Title: {entity.title}")
        print(f"Username: {getattr(entity, 'username', None)}")
    except Exception as e:
        print(f"Error: {e}")
    await client.disconnect()

asyncio.run(main())
