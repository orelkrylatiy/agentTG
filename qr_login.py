import asyncio, os, subprocess
from telethon import TelegramClient
from dotenv import load_dotenv
import qrcode

load_dotenv()
api_id = int(os.getenv("TG_API_ID"))
api_hash = os.getenv("TG_API_HASH")

async def main():
    client = TelegramClient("data/userbot.session", api_id, api_hash)
    await client.connect()
    qr = await client.qr_login()

    img = qrcode.make(qr.url)
    img_path = "/tmp/tg_qr.png"
    img.save(img_path)
    subprocess.Popen(["open", img_path])
    print(f"QR открыт в Preview — отсканируй iPhone камерой")
    print("Telegram → Настройки → Устройства → Добавить устройство\n")

    try:
        await qr.wait(120)
        me = await client.get_me()
        print(f"УСПЕШНО: {me.first_name} (@{me.username}, ID: {me.id})")
    except Exception as e:
        print(f"Ошибка: {e}")
    await client.disconnect()

asyncio.run(main())
