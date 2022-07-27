import traceback
import asyncio
from datetime import datetime
import pytz


def requires_gamba_data(func):
    async def check(self, ctx, *args, **kwargs):
        if ctx.user not in self.gamba_data:
            self.add_new_user(ctx.user)
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


def split_message(message):
    messages = []
    while len(message) > 0:
        messages.append(message[:496])
        message = message[496:]
    return messages


def format_date(date):
    time_values = {
        "seconds": ("minutes", 60),
        "minutes": ("hours", 60),
        "hours": ("days", 24),
        "days": ("months", 30),
        "months": ("years", 12),
        "years": ("centuries", 100),
    }
    seconds = (datetime.now(pytz.UTC) - date.replace(tzinfo=pytz.UTC)).total_seconds()
    info = {"seconds": seconds}
    for label, time_value in time_values.items():
        if info[label] >= time_value[1]:
            info[time_value[0]] = info[label] // time_value[1]
            info[label] %= time_value[1]
        else:
            break

    used_info = list(info.keys())[-2:]
    used_info.reverse()

    return " ".join(f"{int(info[label])} {label}" for label in used_info)
