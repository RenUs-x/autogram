import asyncio
import os
from aiohttp import web

import sss
import monitor_bot
import channel_guard


# =============================
# KEEP RENDER ALIVE SERVER
# =============================
async def health(request):
    return web.Response(text="OK")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)

    await site.start()
    print(f"[WEB] Listening on port {port}")


# =============================
# MAIN APP
# =============================
async def main():

    # ✅ запускаем fake web server
    await start_web_server()

    # ✅ запускаем фарм и получаем сессии
    sessions = await sss.main()

    print(f"[MAIN] Получено аккаунтов: {len(sessions)}")

    # ✅ запускаем ВСЁ параллельно
    await asyncio.gather(
        channel_guard.main(sessions),
        monitor_bot.main(sessions)
    )


if __name__ == "__main__":
    asyncio.run(main())
