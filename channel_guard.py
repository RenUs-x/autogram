import asyncio
import json
import os
from datetime import datetime, timezone, timedelta
from telethon import TelegramClient
from telethon.tl.types import Channel
from telethon.tl.functions.channels import LeaveChannelRequest, GetParticipantRequest

# ================= CONFIG =================

SESSIONS_LOG = "sessions.log"
STATUS_FILE = "status.json"
JOINED_CHANNELS_FILE = "joined_channels.json"

CHECK_INTERVAL = 3600      # каждые 60 минут
LEAVE_AFTER_DAYS = 7       # выход если > 7 дней

# ===========================================


def update_status(name, text):
    data = {}

    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
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
    
def save_joined_channels(data):
    with open(JOINED_CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


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

async def get_participant_join_time(client, entity):
    """
    Пытаемся получить реальную дату вступления аккаунта в канал/группу через Telegram API.
    """
    try:
        result = await client(GetParticipantRequest(channel=entity, participant="me"))
        participant = getattr(result, "participant", None)
        joined_at = getattr(participant, "date", None)
        if joined_at is None:
            return None
        if joined_at.tzinfo is None:
            joined_at = joined_at.replace(tzinfo=timezone.utc)
        return joined_at
    except Exception:
        return None
        
async def resolve_joined_at(client, session_name, entity, joined_channels, all_joined_channels):
    channel_id = getattr(entity, "id", None) or getattr(entity, "channel_id", None)
    if not channel_id:
        return None
        
    key = str(channel_id)
    joined_at = parse_join_time(joined_channels.get(key))
    if joined_at:
        return joined_at

    joined_at = await get_participant_join_time(client, entity)
    if joined_at:
        joined_channels[key] = joined_at.isoformat()
        all_joined_channels[session_name] = joined_channels
        save_joined_channels(all_joined_channels)

    return joined_at
    
async def process_channels_for_client(client, name):
    dialogs = await client.get_dialogs()
    all_joined_channels = load_joined_channels()
    joined_channels = all_joined_channels.get(name, {})

    channels = [
        d for d in dialogs
        if d.is_channel and (
            getattr(d.entity, "broadcast", False)
            or getattr(d.entity, "megagroup", False)
        )
    ]

    now = datetime.now(timezone.utc)
    left_count = 0

    for dialog in channels:
        entity = dialog.entity
        if not isinstance(entity, Channel):
            continue

        joined_at = await resolve_joined_at(client, name, entity, joined_channels, all_joined_channels)
        if not joined_at:
            continue

        age = now - joined_at
        if age >= timedelta(days=LEAVE_AFTER_DAYS):
            await client(LeaveChannelRequest(entity))
            left_count += 1

    return len(channels), left_count
    
# ================= CORE =================

async def check_account(name, api_id, api_hash):

    session = f"{name}_session"

    client = TelegramClient(session, api_id, api_hash)

    await client.connect()

    if not await client.is_user_authorized():
        update_status(name, "NOT AUTH ❌")
        await client.disconnect()
        return

    total, left_count = await process_channels_for_client(client, name)

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
                channels_count, left_count = await process_channels_for_client(client, name)
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
    
