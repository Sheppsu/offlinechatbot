import sys
import traceback
import asyncio
from datetime import datetime


def print(message):
    # TODO: timezone
    sys.stdout.write(f"[{datetime.now().isoformat()}]{message}\n")
    sys.stdout.flush()


def cooldown(user_cd=10, cmd_cd=5):
    def _cooldown(func):
        async def check(self, ctx, *args, **kwargs):
            if ctx.user is not None and self.is_on_cooldown(func.__name__, ctx.user, user_cd, cmd_cd):
                return
            return await func(self, ctx, *args, **kwargs)

        return check

    return _cooldown


def requires_gamba_data(func):
    async def check(self, ctx, *args, **kwargs):
        if ctx.user not in self.gamba_data:
            self.add_new_user(ctx.user)
        return await func(self, ctx, *args, **kwargs)

    return check


def requires_dev(func):
    async def check(self, ctx, *args, **kwargs):
        if ctx.user != "sheepposu":
            return await self.send_message(ctx.channel, f"@{ctx.user} This is a dev only command")
        return await func(self, ctx, *args, **kwargs)

    return check


async def do_timed_event(wait, callback, *args, **kwargs):
    await asyncio.sleep(wait)
    await callback(*args, **kwargs)


def future_callback(future):
    if future.cancelled():
        return
    try:
        result = future.result()
        if result:
            print(result)
    except:
        traceback.print_exc()


def format_date(date):
    minutes = (datetime.now() - date).total_seconds() // 60
    hours = 0
    days = 0
    if minutes >= 60:
        hours = minutes // 60
        minutes = minutes % 60
        if hours >= 24:
            days = hours // 24
            hours = hours % 24
    elif minutes == 0:
        return f"{(datetime.now() - date).seconds} seconds"
    return ((f"{int(days)} day(s) " if days != 0 else "") + (f" {int(hours)} hour(s) " if hours != 0 else "") + (
        f" {int(minutes)} minute(s)" if minutes != 0 else "")).strip()
