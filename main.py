if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(override=True)

    from bot import BotManager
    import sys
    import asyncio
    import logging

    logging.basicConfig(
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        level=logging.DEBUG if "--debug" in sys.argv else logging.INFO
    )

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    loop = asyncio.new_event_loop()
    manager = BotManager(loop)
    loop.run_until_complete(manager.run())
