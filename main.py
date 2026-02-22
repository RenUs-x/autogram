import asyncio
import sss
import monitor_bot
import channel_guard
import keep_alive


async def main():

    # запускаем fake web server (ОБЯЗАТЕЛЬНО)
    keep_alive.start()

    # запускаем фарм и получаем сессии
    sessions = await sss.main()

    # запускаем фоновые сервисы
    await asyncio.gather(
        channel_guard.main(sessions),
        monitor_bot.main(sessions)
    )


if __name__ == "__main__":
    asyncio.run(main())
