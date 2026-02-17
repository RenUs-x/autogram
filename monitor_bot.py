import asyncio
import json
import os
import aiohttp
from aiohttp import web

# ===== НАСТРОЙКИ =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
STATUS_FILE = "status.json"

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
last_update_id = 0
last_status = {}

# ===== Чтение статусов =====
def load_status():
    if not os.path.exists(STATUS_FILE):
        return {}
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

# ===== Отправка сообщения =====
async def send_message(text):
    async with aiohttp.ClientSession() as session:
        await session.post(
            f"{API_URL}/sendMessage",
            json={
                "chat_id": ADMIN_ID,
                "text": text
            }
        )

# ===== Команда /start =====
async def handle_start():
    status_data = load_status()

    if not status_data:
        await send_message("Нет данных о статусах.")
        return

    text = "📊 Status:\n\n"
    for name, status in status_data.items():
        text += f"{name} — {status}\n"

    await send_message(text)

# ===== Проверка изменения статусов =====
async def watch_status_changes():
    global last_status

    while True:
        current = load_status()

        for name, status in current.items():
            if name in last_status and last_status[name] != status:
                await send_message(f"{name} — {status}")

        last_status = current
        await asyncio.sleep(5)

# ===== Polling =====
async def poll():
    global last_update_id

    while True:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_URL}/getUpdates?offset={last_update_id + 1}"
            ) as response:
                data = await response.json()

        for update in data.get("result", []):
            last_update_id = update["update_id"]

            message = update.get("message")
            if not message:
                continue

            if message["chat"]["id"] != ADMIN_ID:
                continue

            if message.get("text") == "/start":
                await handle_start()

        await asyncio.sleep(2)


async def health(request):
    return web.Response(text="OK")

async def start_web():
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 10000)
    await site.start()

# ===== MAIN =====
async def main():
    global last_status
    last_status = load_status()

    await asyncio.gather(
        poll(),
        watch_status_changes(),
        start_web()
    )

if __name__ == "__main__":
    asyncio.run(main())
