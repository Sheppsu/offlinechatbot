if __name__ == "__main__":
    from bot import Bot
    import sys
    import asyncio
    import logging

    logging.basicConfig(
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        level=logging.DEBUG if "--debug" in sys.argv else logging.INFO
    )

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    async def run():
        await bot.setup()
        await bot.run_forever()

    loop = asyncio.new_event_loop()
    bot = Bot(loop)
    loop.run_until_complete(run())
