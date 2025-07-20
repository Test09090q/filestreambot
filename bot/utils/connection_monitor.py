import asyncio
from bot import TelegramBot, _streaming_bots, logger
from bot.config import Util
from .restart import emergency_restart


async def check_bot_connection(bot, bot_name="Main Bot"):
    try:
        await bot.get_me()
        return True
    except ConnectionError:
        logger.error("Connection error detected for %s", bot_name)
        return False
    except Exception as e:
        error_message = str(e)
        if "Cannot send requests while disconnected" in error_message:
            logger.error("Disconnection detected for %s", bot_name)
            return False
        logger.warning("Non-connection error for %s: %s", bot_name, error_message)
        return True


async def monitor_connections():
    check_interval = Util.CONNECTION_CHECK_INTERVAL
    consecutive_failures = 0
    max_failures = 3

    logger.info(
        "Started connection monitoring with %s second intervals", check_interval
    )

    while True:
        try:
            await asyncio.sleep(check_interval)

            main_bot_ok = await check_bot_connection(TelegramBot, "Main Bot")

            streaming_bots_ok = 0
            total_streaming_bots = len(_streaming_bots)

            for i, bot in enumerate(_streaming_bots):
                if await check_bot_connection(bot, f"Streaming Bot {i+1}"):
                    streaming_bots_ok += 1

            if main_bot_ok and (total_streaming_bots == 0 or streaming_bots_ok > 0):
                consecutive_failures = 0
                logger.info(
                    "Connection check passed - Main: %s, Streaming: %s/%s",
                    "OK" if main_bot_ok else "FAIL",
                    streaming_bots_ok,
                    total_streaming_bots,
                )
            else:
                consecutive_failures += 1
                logger.warning(
                    "Connection check failed (%s/%s) - Main: %s, Streaming: %s/%s",
                    consecutive_failures,
                    max_failures,
                    "OK" if main_bot_ok else "FAIL",
                    streaming_bots_ok,
                    total_streaming_bots,
                )

                if consecutive_failures >= max_failures:
                    logger.critical(
                        "Maximum consecutive connection failures reached (%s), triggering emergency restart",
                        consecutive_failures,
                    )
                    emergency_restart("Multiple consecutive connection check failures")

        except Exception as e:
            logger.error("Error in connection monitoring: %s", e)
            await asyncio.sleep(60)
