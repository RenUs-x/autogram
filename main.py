import asyncio
import sss
import monitor_bot
import channel_guard

async def main():
    await asyncio.gather(
        sss.main(),
        channel_guard.main(),
        monitor_bot.main()
    )

if __name__ == "__main__":
    asyncio.run(main())
