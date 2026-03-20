import asyncio
import datetime
import io
import re
import time

from telethon import events
from telethon.errors import FloodWaitError
from telethon.events import NewMessage
from telethon.tl.custom.message import Message
from telethon.tl.types import KeyboardButtonCallback, KeyboardButtonStyle

from bot import TelegramBot, logger
from bot.config import Telegram
from bot.db.sql import query_msg
from bot.db.support import users_info


@TelegramBot.on(NewMessage(incoming=True, pattern=r"^/stats$"))
async def subscribers_count(event: NewMessage.Event | Message):
    user_id = str(event.sender_id)
    if user_id not in str(Telegram.OWNER_ID):
        return
    wait_msg = "__Calculating, please wait...__"
    msg = await event.reply(wait_msg)
    active, blocked = await users_info()
    stats_msg = f"**Stats**\nActive: `{active}`\nBlocked / Deleted: `{blocked}`"
    await msg.edit(stats_msg)


broadcast_lock = asyncio.Lock()
success = 0
failed = 0
completed = 0
t_users = 0
start_time = 0
cancel_broadcast = False


async def send_one(chat_id, msg):
    global success, failed
    while True:
        try:
            await TelegramBot.send_message(chat_id, msg)
            success += 1
            return "success"
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except Exception as e:
            failed += 1
            return f"{chat_id}: {str(e)}"


@TelegramBot.on(events.CallbackQuery(data=re.compile(b"brd_")))
async def broadcast_callback(event):
    global success, failed, completed, t_users, start_time, cancel_broadcast
    query = event.data.decode()
    if query == "brd_pgrs":
        time_taken = datetime.timedelta(seconds=int(time.time() - start_time))
        await event.answer(
            f"Broadcast Progress\n\nTotal: {t_users}\nCompleted: {completed}\nSuccess: {success}\nFailed: {failed}\nTime Taken: {time_taken}",
            alert=True,
        )
    elif query == "brd_cncl":
        cancel_broadcast = True
        await event.answer("Cancelling broadcast...", alert=True)


@TelegramBot.on(NewMessage(incoming=True, pattern=r"^/broadcast$"))
async def send_text(event: NewMessage.Event | Message):
    global success, failed, completed, t_users, start_time, cancel_broadcast
    user_id = str(event.sender_id)
    if user_id not in str(Telegram.OWNER_ID):
        return

    if (
        (" " not in event.text)
        and ("broadcast" in event.text)
        and (event.message.reply_to_msg_id is not None)
    ):
        if broadcast_lock.locked():
            return await event.reply("__A broadcast is already in progress...__")

        async with broadcast_lock:
            success = failed = completed = 0
            cancel_broadcast = False
            start_time = time.time()

            users = await query_msg()
            t_users = len(users)

            msg = await event.get_reply_message()
            bc_log = ""

            buttons = [
                [
                    KeyboardButtonCallback(
                        text="📊 Progress",
                        data="brd_pgrs",
                        style=KeyboardButtonStyle(bg_primary=True),
                    ),
                    KeyboardButtonCallback(
                        text="❌ Cancel",
                        data="brd_cncl",
                        style=KeyboardButtonStyle(bg_danger=True),
                    ),
                ]
            ]

            await TelegramBot.send_message(event.sender_id, msg)
            status_msg = await event.reply("__Broadcast started...__", buttons=buttons)

            semaphore = asyncio.Semaphore(20)

            async def sem_send(u_id, m):
                async with semaphore:
                    return await send_one(u_id, m)

            tasks = [sem_send(int(user[0]), msg) for user in users]

            try:
                for coro in asyncio.as_completed(tasks):
                    if cancel_broadcast:
                        break
                    result = await coro
                    completed += 1

                    if result != "success":
                        bc_log += f"{result}\n"

                    if completed % 50 == 0:
                        logger.info("Broadcast: %s/%s", completed, t_users)

            except asyncio.CancelledError:
                logger.info("Broadcast cancelled")

            time_taken = datetime.timedelta(seconds=int(time.time() - start_time))

            await status_msg.delete()
            final_msg = (
                f"**Broadcast Completed**\n\n"
                f"Completed: `{completed}/{t_users}`\n"
                f"Success: `{success}`\n"
                f"Failed: `{failed}`\n"
                f"Time Taken: `{time_taken}`"
            )

            await TelegramBot.send_message(event.sender_id, final_msg)

            if bc_log:
                log_file = io.BytesIO(bc_log.encode())
                log_file.name = "broadcast_failed.txt"
                await TelegramBot.send_file(
                    event.sender_id, log_file, caption="Failed users log"
                )
    else:
        reply_error = (
            "`Use this command as a reply to any telegram message without any spaces.`"
        )
        msg = await event.reply(reply_error)
        await asyncio.sleep(8)
        await msg.delete()
