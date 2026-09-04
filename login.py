"""
Run this script directly in your terminal to authorize the Telegram userbot session.
Usage: python login.py
"""
import asyncio
import logging
from telethon import TelegramClient
from telethon.errors import (
    PhoneNumberInvalidError, PhoneCodeInvalidError,
    PhoneCodeExpiredError, SessionPasswordNeededError, FloodWaitError
)
from dotenv import load_dotenv
import os

load_dotenv()

logging.basicConfig(level=logging.DEBUG)

api_id = int(os.getenv("TG_API_ID"))
api_hash = os.getenv("TG_API_HASH")
phone = os.getenv("TG_PHONE")

print(f"api_id={api_id}")
print(f"api_hash={api_hash[:6]}...")
print(f"phone={phone}")

async def main():
    client = TelegramClient("data/userbot.session", api_id, api_hash)
    print("\nConnecting to Telegram...")
    await client.connect()
    print(f"Connected: {client.is_connected()}")

    print(f"\nSending code to {phone}...")
    try:
        sent = await client.send_code_request(phone)
        print(f"Code type: {sent.type.__class__.__name__}")
        print(f"Next type: {sent.next_type.__class__.__name__ if sent.next_type else 'None'}")
        print(f"Timeout: {sent.timeout}")
    except FloodWaitError as e:
        print(f"FLOOD WAIT: need to wait {e.seconds} seconds before trying again!")
        await client.disconnect()
        return
    except PhoneNumberInvalidError:
        print(f"ERROR: phone number {phone} is invalid!")
        await client.disconnect()
        return
    except Exception as e:
        print(f"ERROR sending code: {type(e).__name__}: {e}")
        await client.disconnect()
        return

    code = input("\nEnter the code from Telegram: ")

    try:
        await client.sign_in(phone, code)
        me = await client.get_me()
        print(f"\nSuccess! Logged in as: {me.first_name} (@{me.username}, ID: {me.id})")
    except PhoneCodeInvalidError:
        print("ERROR: code is wrong!")
    except PhoneCodeExpiredError:
        print("ERROR: code expired, run the script again")
    except SessionPasswordNeededError:
        password = input("2FA password required: ")
        await client.sign_in(password=password)
        me = await client.get_me()
        print(f"\nSuccess! Logged in as: {me.first_name} (@{me.username}, ID: {me.id})")
    except Exception as e:
        print(f"ERROR signing in: {type(e).__name__}: {e}")

    await client.disconnect()

asyncio.run(main())
