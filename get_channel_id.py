"""
Get channel ID from link or username.

Usage:
    python get_channel_id.py <channel_link_or_username>
    
Examples:
    python get_channel_id.py https://t.me/+ucoAOCsXCwk3ZmFi
    python get_channel_id.py https://t.me/durov
    python get_channel_id.py @durov
    python get_channel_id.py durov
"""
import asyncio
import os
import sys
from telethon import TelegramClient
from dotenv import load_dotenv

load_dotenv()

api_id = int(os.getenv("TG_API_ID", "0"))
api_hash = os.getenv("TG_API_HASH", "")

if not api_id or not api_hash:
    print("❌ Error: TG_API_ID and TG_API_HASH must be set in .env file")
    sys.exit(1)


async def main():
    if len(sys.argv) < 2:
        print("Usage: python get_channel_id.py <channel_link_or_username>")
        print("\nExamples:")
        print("  python get_channel_id.py https://t.me/+ucoAOCsXCwk3ZmFi")
        print("  python get_channel_id.py https://t.me/durov")
        print("  python get_channel_id.py @durov")
        print("  python get_channel_id.py durov")
        sys.exit(1)

    channel_input = sys.argv[1]

    client = TelegramClient("data/userbot.session", api_id, api_hash)
    await client.connect()
    
    try:
        # Get entity
        entity = await client.get_entity(channel_input)
        
        # Format channel ID for .env file
        channel_id = entity.id
        if hasattr(channel_id, 'channel_id'):
            # It's a ChannelFull object
            channel_id = channel_id.channel_id
        
        # Ensure proper format for userbot
        if isinstance(channel_id, int) and channel_id > 0:
            # Convert to superchannel format
            channel_id = int(f"-100{channel_id}")
        
        print(f"\n{'='*50}")
        print(f"📢 Channel Found:")
        print(f"{'='*50}")
        print(f"Title:      {entity.title}")
        print(f"Username:   @{getattr(entity, 'username', 'N/A')}")
        print(f"ID:         {channel_id}")
        print(f"{'='*50}")
        print(f"\n✅ Add to .env:")
        print(f'   MONITORED_CHANNELS="{channel_id}:YourTitle:outreach"')
        print(f"\n✅ Or use in outreach.py:")
        print(f"   python outreach.py 10 {channel_id}")
        
    except ValueError as e:
        print(f"❌ Error: Channel not found. Make sure you're joined to this channel.")
        print(f"   Details: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
