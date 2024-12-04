import asyncio
from datetime import datetime
import pytz
import logging
from typing import Iterable, Callable, TypeVar
from time import time


log = logging.getLogger(__name__)


async def wait_and_call(wait, callback, *args, **kwargs):
    await asyncio.sleep(wait)
    await callback(*args, **kwargs)


def split_message(message):
    messages = []
    while len(message) > 0:
        messages.append(message[:495].strip())
        message = message[495:]
    return messages


def format_date(date: datetime | int):
    seconds = round(time() - date) if isinstance(date, int) else \
        (datetime.now(pytz.UTC) - date.replace(tzinfo=pytz.UTC)).total_seconds()

    return format_time_length(seconds)


def format_time_length(seconds: float):
    time_values = {
        "seconds": ("minutes", 60),
        "minutes": ("hours", 60),
        "hours": ("days", 24),
        "days": ("months", 30),
        "months": ("years", 12),
        "years": ("centuries", 100),
    }

    info = {"seconds": round(seconds)}
    for label, time_value in time_values.items():
        if info[label] >= time_value[1]:
            info[time_value[0]] = info[label] // time_value[1]
            info[label] %= time_value[1]
        else:
            break

    used_info = list(info.keys())[-2:]
    used_info.reverse()

    return " ".join(f"{int(info[label])} {label}" for label in used_info)


def parse_irc_string(string):
    return string.replace(r"\s", " ").replace(r"\:", ";").replace("\\\\", "\\")


_T1 = TypeVar("_T1")
_T2 = TypeVar("_T2")


def matching_zip(items_a: Iterable[_T1], items_b: Iterable[_T2], cmp: Callable[[_T1, _T2], int]):
    try:
        iter_a = iter(items_a)
        iter_b = iter(items_b)
        a = next(iter_a)
        b = next(iter_b, None)
        while True:
            if b is None:
                iter_b = iter(items_b)
                b = next(iter_b)

            diff = cmp(a, b)
            if diff == 0:
                yield a, b
                a = next(iter_a)
                b = next(iter_b, None)
            elif diff < 0:
                a = next(iter_a)
            else:
                b = next(iter_b, None)
    except StopIteration:
        return
