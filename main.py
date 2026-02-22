import asyncio
import sss
import monitor_bot
import channel_guard

async def main():
    # 1. запускаем фарм и получаем аккаунты
    sessions = await sss.main()

    # 2. запускаем фоновые сервисы
    await asyncio.gather(
        channel_guard.main(sessions),
        monitor_bot.main(sessions)
    )

if __name__ == "__main__":
    asyncio.run(main())
