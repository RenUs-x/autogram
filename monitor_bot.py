import asyncio
import json
import os
import aiohttp
from aiohttp import web

# ===== НАСТРОЙКИ =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS").split(",")]
STATUS_FILE = "status.json"

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
last_update_id = 0
last_status = {}


# ===== Чтение/нормализация статусов =====
def normalize_status_data(raw_data):
    normalized = {}
    if not isinstance(raw_data, dict):
        return normalized

    for name, value in raw_data.items():
        if isinstance(value, dict):
            normalized[name] = {
                "status": value.get("status", "—"),
                "guard": value.get("guard", "—")
            }
        else:
            normalized[name] = {
                "status": value,
                "guard": "—"
            }

    return normalized


def load_status():
    if not os.path.exists(STATUS_FILE):
        return {}
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return normalize_status_data(json.load(f))
    except Exception:
        return {}


# ===== Отправка сообщения =====
async def send_message(text):
    async with aiohttp.ClientSession() as session:
        for admin_id in ADMIN_IDS:
            await session.post(
                f"{API_URL}/sendMessage",
                json={
                    "chat_id": admin_id,
                    "text": text
                }
            )


def format_status_view(status_data, field):
    title = "📊 Main Status" if field == "status" else "🛡 Guard Status"
    lines = [f"{title}:\n"]

    for name, data in status_data.items():
        lines.append(f"{name} — {data.get(field, '—')}")

    return "\n".join(lines)


async def send_status_view(chat_id, field, message_id=None):
    status_data = load_status()

    if not status_data:
        text = "Нет данных о статусах."
    else:
        text = format_status_view(status_data, field)

    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "📊 Status", "callback_data": "show_status"},
                {"text": "🛡 Guard", "callback_data": "show_guard"}
            ]]
        }
    }

    method = "sendMessage"
    if message_id is not None:
        method = "editMessageText"
        payload["message_id"] = message_id

    async with aiohttp.ClientSession() as session:
        await session.post(f"{API_URL}/{method}", json=payload)


# ===== Команда /start =====
async def handle_start(chat_id):
    await send_status_view(chat_id, field="status")


# ===== Проверка изменения статусов =====
async def watch_status_changes():
    global last_status

    while True:
        current = load_status()

        if not last_status:
            last_status = current
            await asyncio.sleep(5)
            continue

        all_names = set(last_status.keys()) | set(current.keys())

        for name in all_names:
            prev_data = last_status.get(name, {"status": "—", "guard": "—"})
            cur_data = current.get(name, {"status": "—", "guard": "—"})

            if prev_data.get("status") != cur_data.get("status"):
                await send_message(f"{name} — STATUS: {cur_data.get('status')}")

            if prev_data.get("guard") != cur_data.get("guard"):
                await send_message(f"{name} — GUARD: {cur_data.get('guard')}")

        last_status = current
        await asyncio.sleep(5)


async def answer_callback_query(callback_query_id):
    async with aiohttp.ClientSession() as session:
        await session.post(
            f"{API_URL}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id}
        )


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

            callback_query = update.get("callback_query")
            if callback_query:
                message = callback_query.get("message", {})
                chat = message.get("chat", {})
                chat_id = chat.get("id")
                message_id = message.get("message_id")
                callback_data = callback_query.get("data")
                callback_query_id = callback_query.get("id")

                if chat_id in ADMIN_IDS and callback_data in {"show_status", "show_guard"}:
                    field = "status" if callback_data == "show_status" else "guard"
                    await send_status_view(chat_id, field, message_id=message_id)

                if callback_query_id:
                    await answer_callback_query(callback_query_id)
                continue

            message = update.get("message")
            if not message:
                continue

            chat_id = message["chat"]["id"]

            if chat_id not in ADMIN_IDS:
                continue

            if message.get("text") == "/start":
                await handle_start(chat_id)

        await asyncio.sleep(2)


# ===== HEALTH ENDPOINT =====
async def health(request):
    return web.Response(text="OK")


async def start_web():
    app = web.Application()
    app.router.add_get("/", health)

    port = int(os.getenv("PORT", 10000))

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    try:
        await site.start()
    except OSError as e:
        if e.errno == 98:
            return
        raise


# ===== MAIN =====
async def main(sessions=None):
    global last_status
    last_status = load_status()

    await asyncio.gather(
        poll(),
        watch_status_changes(),
        start_web()
    )


if __name__ == "__main__":
    asyncio.run(main())
