import asyncio
import sss
import monitor_bot

async def main():
    await asyncio.gather(
        sss.main(),
        monitor_bot.main()
    )

if __name__ == "__main__":
    asyncio.run(main())
