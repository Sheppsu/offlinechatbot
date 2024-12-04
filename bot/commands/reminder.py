from .base import CommandBot, CommandArg
from ..context import MessageContext, JoinContext
from ..database import UserReminder
from ..util import format_date
from ..bot import BotMeta

from datetime import datetime, timedelta, timezone
from time import time


class ReminderBot(CommandBot, metaclass=BotMeta):
    command_manager = CommandBot.command_manager

    def __init__(self):
        self.old_reminders: list[UserReminder] = None  # type: ignore

    async def on_setup(self, ctx):
        self.old_reminders = await self.db.get_reminders()

    async def on_join(self, ctx: JoinContext):
        reminders = [reminder for reminder in self.old_reminders if reminder.channel.user.username == ctx.channel]
        for reminder in reminders:
            self.set_reminder_event(reminder)
            self.old_reminders.remove(reminder)

    async def send_reminder_msg(self, reminder: UserReminder):
        user = await self.db.get_user(reminder.user.id, reminder.user.username)
        channel = await self.db.get_channel(reminder.channel.user.id)
        await self.send_message(
            channel.user.username,
            f"@{user.username} DinkDonk Reminder! {reminder.message}"
        )
        await self.db.finish_reminder(reminder.id)

    def set_reminder_event(self, reminder: UserReminder):
        length = round(max(0.0, (reminder.remind_at - time())))
        self.call_later(length, self.send_reminder_msg, reminder)

    async def time_text_to_timedelta(self, ctx: MessageContext, text: str) -> timedelta | None:
        time_multipliers = {
            "s": 1,
            "m": 60,
            "h": 60 * 60,
            "d": 60 * 60 * 24,
            "w": 60 * 60 * 24 * 7
        }

        if (cc := text.count(":")) > 0:
            if cc > 1:
                return await self.send_message(ctx.channel, "Must specify times in XX:XX format Nerdge")

            tz = await self.db.get_user_timezone(ctx.user_id)
            if tz is None:
                return await self.send_message(
                    ctx.channel,
                    "You need to link a timezone with !linktz to use time reminders"
                )

            try:
                hour, minute = tuple(map(int, text.split(":")))
            except ValueError:
                return await self.send_message(ctx.channel, "Not a valid integer Nerdge")

            tz = timezone(tz.timezone)
            now = datetime.now(tz=tz)
            future = now.replace(hour=hour, minute=minute, second=0)
            if now >= future:
                future += timedelta(hours=24)
            return future - now

        suffix = text[-1].lower()
        if suffix not in time_multipliers:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} the time must end with s, m, h, d, or w Nerdge"
            )

        try:
            return timedelta(seconds=round(float(text[:-1]) * time_multipliers[suffix]))
        except ValueError:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} not a valid number Nerdge")

    @command_manager.command(
        "remind",
        "Set a reminder for later. Can set with relative time or an absolute time.",
        [
            CommandArg(
                "when",
                "either a relative time (e.g. 90s, 20m, 1.5h, 3.2d) or an absolute time (e.g. 20:00). "
                "To use absolute times you must link your timezone with !linktz."
            ),
            CommandArg("message", is_optional=True)
        ],
        aliases=["reminder", "remindme"]
    )
    async def set_reminder(self, ctx: MessageContext):
        args = ctx.get_args()
        if len(args) == 0:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Must give a time (10s, 20m, 1.5h, 3.2d, ...) Chatting"
            )

        now = time()
        length = await self.time_text_to_timedelta(ctx, args[0])
        if not isinstance(length, timedelta):
            return
        if length.total_seconds() < 60:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Reminder must be at least a minute Nerdge"
            )

        timestamp = round(now + length.total_seconds())
        reminder = await self.db.create_reminder(
            ctx.user_id,
            ctx.sending_user,
            timestamp,
            " ".join(args[1:]),
            ctx.room_id
        )
        self.set_reminder_event(reminder)

        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} Set reminder to occur in {format_date(timestamp)} YIPPEE"
        )
