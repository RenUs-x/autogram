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

    channels = []
    now = datetime.now(timezone.utc)

    left_count = 0

    for dialog in dialogs:

        entity = dialog.entity

        if not isinstance(entity, Channel):
            continue

        if getattr(entity, "broadcast", False) or getattr(entity, "megagroup", False):

            channels.append(entity)

            try:
                full = await client.get_entity(entity.id)

                # приблизительный возраст
                date = dialog.date

                if not date:
                    continue

                age = now - date

                if age > timedelta(days=LEAVE_AFTER_DAYS):

                    await client(LeaveChannelRequest(entity))

                    left_count += 1

            except:
                pass

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

            dialogs = await client.get_dialogs()

            channels = [
                d for d in dialogs
                if d.is_channel and not d.entity.broadcast is False
            ]

            print(f"{name}: {len(channels)} каналов")

        await asyncio.sleep(600)

# ================= MAIN =================
async def main(sessions):
    await guard_loop(sessions)
    
if __name__ == "__main__":
    asyncio.run(main())
    
