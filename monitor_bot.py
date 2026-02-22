+import asyncio
+import json
+import os
+import aiohttp
+from aiohttp import web
+
+# ===== НАСТРОЙКИ =====
+BOT_TOKEN = os.getenv("BOT_TOKEN")
+ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS").split(",")]
+STATUS_FILE = "status.json"
+
+API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
+last_update_id = 0
+last_status = {}
+
+# ===== Чтение статусов =====
+def load_status():
+    if not os.path.exists(STATUS_FILE):
+        return {}
+    try:
+        with open(STATUS_FILE, "r", encoding="utf-8") as f:
+            return json.load(f)
+    except:
+        return {}
+
+# ===== Отправка сообщения =====
+async def send_message(text):
+    async with aiohttp.ClientSession() as session:
+        for admin_id in ADMIN_IDS:
+            await session.post(
+                f"{API_URL}/sendMessage",
+                json={
+                    "chat_id": admin_id,
+                    "text": text
+                }
+            )
+
+# ===== Команда /start =====
+async def handle_start(chat_id):
+    status_data = load_status()
+
+    if not status_data:
+        await send_message("Нет данных о статусах.")
+        return
+
+    text = "📊 Status:\n\n"
+    for name, status in status_data.items():
+        text += f"{name} — {status}\n"
+
+    async with aiohttp.ClientSession() as session:
+        await session.post(
+            f"{API_URL}/sendMessage",
+            json={
+                "chat_id": chat_id,
+                "text": text
+            }
+        )
+
+# ===== Проверка изменения статусов =====
+async def watch_status_changes():
+    global last_status
+
+    while True:
+        current = load_status()
+
+        # если это первый запуск — просто запоминаем
+        if not last_status:
+            last_status = current
+            await asyncio.sleep(5)
+            continue
+
+        for name, status in current.items():
+            if name in last_status and last_status[name] != status:
+                await send_message(f"{name} — {status}")
+
+        last_status = current
+        await asyncio.sleep(5)
+        
+# ===== Polling =====
+async def poll():
+    global last_update_id
+
+    while True:
+        async with aiohttp.ClientSession() as session:
+            async with session.get(
+                f"{API_URL}/getUpdates?offset={last_update_id + 1}"
+            ) as response:
+                data = await response.json()
+
+        for update in data.get("result", []):
+            last_update_id = update["update_id"]
+
+            message = update.get("message")
+            if not message:
+                continue
+
+            chat_id = message["chat"]["id"]
+
+            if chat_id not in ADMIN_IDS:
+                continue
+
+            if message.get("text") == "/start":
+                await handle_start(chat_id)
+
+        await asyncio.sleep(2)
+
+# ===== HEALTH ENDPOINT =====
+async def health(request):
+    return web.Response(text="OK")
+
+async def start_web():
+    app = web.Application()
+    app.router.add_get("/", health)
+
+    port = int(os.getenv("PORT", 10000))
+
+    runner = web.AppRunner(app)
+    await runner.setup()
+    site = web.TCPSite(runner, "0.0.0.0", port)
+    await site.start()
+
+# ===== MAIN =====
+async def main(sessions=None):
+    global last_status
+    last_status = load_status()
+
+    await asyncio.gather(
+        poll(),
+        watch_status_changes(),
+        start_web()
+    )
+
+if __name__ == "__main__":
+    asyncio.run(main())
+
