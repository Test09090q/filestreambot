import asyncio
from telethon.errors import FloodWaitError
from bot import TelegramBot, logger
from bot.db.sql import del_user, query_msg


async def users_info():
    active = 0
    blocked = 0
    identity = await query_msg()

    semaphore = asyncio.Semaphore(50)

    async def check_user(user_id):
        nonlocal active, blocked
        while True:
            try:
                async with semaphore:
                    async with TelegramBot.action(int(user_id[0]), "typing"):
                        await asyncio.sleep(0.1)
                active += 1
                return
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except Exception as e:
                if "disconnected".lower() in str(e).lower():
                    logger.info("User id %s - Bot disconnected: %s", user_id[0], e)
                    return
                blocked += 1
                await del_user(user_id)
                logger.info("Deleted user id %s from broadcast list: %s", user_id[0], e)
                return

    tasks = [check_user(user_id) for user_id in identity]
    await asyncio.gather(*tasks)

    return active, blocked
