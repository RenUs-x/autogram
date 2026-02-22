import asyncio
import json
import os
from datetime import datetime, timezone, timedelta
from telethon import TelegramClient
from telethon.tl.types import Channel
from telethon.tl.functions.channels import LeaveChannelRequest

# ================= CONFIG =================

SESSIONS_LOG = "sessions.log"
STATUS_FILE = "status.json"
JOINED_CHANNELS_FILE = "joined_channels.json"

CHECK_INTERVAL = 1800      # каждые 30 минут
LEAVE_AFTER_DAYS = 7       # выход если > 7 дней

# ===========================================


def update_status(name, text):
    data = {}

    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            pass

    data[name] = text

    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def sessions_log_read():
    entries = {}

    if not os.path.exists(SESSIONS_LOG):
        return entries

    with open(SESSIONS_LOG, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(";")
            if len(parts) >= 3:
                entries[parts[0]] = (int(parts[1]), parts[2])

    return entries

def load_joined_channels():
    if not os.path.exists(JOINED_CHANNELS_FILE):
        return {}
    try:
        with open(JOINED_CHANNELS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def parse_join_time(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

# ================= CORE =================

async def check_account(name, api_id, api_hash):

    session = f"{name}_session"

    client = TelegramClient(session, api_id, api_hash)

    await client.connect()

    if not await client.is_user_authorized():
        update_status(name, "NOT AUTH ❌")
        await client.disconnect()
        return

    dialogs = await client.get_dialogs()
    joined_channels = load_joined_channels().get(name, {})

    channels = []
    now = datetime.now(timezone.utc)

    left_count = 0

    for dialog in dialogs:

        entity = dialog.entity

        if not isinstance(entity, Channel):
            continue

        if getattr(entity, "broadcast", False) or getattr(entity, "megagroup", False):

            channels.append(entity)

            channel_id = getattr(entity, "id", None) or getattr(entity, "channel_id", None)
            if not channel_id:
                continue

            joined_at = parse_join_time(joined_channels.get(str(channel_id)))
            if not joined_at:
                continue

            age = now - joined_at

            if age > timedelta(days=LEAVE_AFTER_DAYS):

                await client(LeaveChannelRequest(entity))

                left_count += 1


    total = len(channels)

    update_status(
        name,
        f"GUARD 🛡 | Channels: {total} | Left: {left_count}"
    )

    await client.disconnect()


# ================= LOOP =================
async def guard_loop(sessions):

    while True:

        for s in sessions:

            client = s["client"]
            name = s["name"]

            try:
                dialogs = await client.get_dialogs()
                joined_channels = load_joined_channels().get(name, {})                

                channels = [
                    d for d in dialogs
                    if d.is_channel and (
                        getattr(d.entity, "broadcast", False)
                        or getattr(d.entity, "megagroup", False)
                    )
                ]

                channels_count = len(channels)
                now = datetime.now(timezone.utc)
                left_count = 0

                for dialog in channels:
                    channel_id = getattr(dialog.entity, "id", None) or getattr(dialog.entity, "channel_id", None)
                    if not channel_id:
                        continue

                    joined_at_raw = joined_channels.get(str(channel_id))
                    joined_at = parse_join_time(joined_at_raw)
                    if not joined_at:
                        # Если время вступления неизвестно, канал не трогаем.
                        continue

                    age = now - joined_at
                    if age > timedelta(days=LEAVE_AFTER_DAYS):
                        await client(LeaveChannelRequest(dialog.entity))
                        left_count += 1

                print(f"{name}: {channels_count} каналов")
                update_status(
                    f"{name} [GUARD]",
                    f"Channels: {channels_count} | Left: {left_count}"
                )
            except Exception as e:
                print(f"{name}: guard error: {e}")
                update_status(f"{name} [GUARD]", "GUARD ERROR ❌")
                
        await asyncio.sleep(CHECK_INTERVAL)

# ================= MAIN =================
async def main(sessions):
    await guard_loop(sessions)
    
if __name__ == "__main__":
    asyncio.run(main())
    
