from .base import CommandBot, Cooldown, CommandArg
from ..bot import BotMeta

from datetime import datetime
from pytz import all_timezones, timezone


class TimezoneBot(CommandBot, metaclass=BotMeta):
    command_manager = CommandBot.command_manager

    def __init__(self):
        self.tz_abbreviations = {}
        for name in all_timezones:
            tzone = timezone(name)
            for _, _, abbr in getattr(tzone, "_transition_info", [[None, None, datetime.now(tzone).tzname()]]):
                if abbr not in self.tz_abbreviations:
                    self.tz_abbreviations[abbr] = []
                if name in self.tz_abbreviations[abbr]:
                    continue
                self.tz_abbreviations[abbr].append(name)

    @command_manager.command(
        "validtz",
        "Send a link to help find a valid timezone for !linktz"
    )
    async def valid_timezones(self, ctx):
        await self.send_message(
            ctx.channel,
            "Having trouble linking your timezone? Here's a list of valid timezones (use the text on the left column): "
            "https://www.ibm.com/docs/en/cloudpakw3700/2.3.0.0?topic=SS6PD2_2.3.0/doc/psapsys_restapi/time_zone_list.html"
        )

    @command_manager.command(
        "linktz",
        "Link a timezone to yourself. Used mainly for !utime.",
        [
            CommandArg(
                "timezone",
                "Most likely to recognize timezones in Continent/City format. For help use !validtz"
            )
        ],
        cooldown=Cooldown(0, 3)
    )
    async def link_timezone(self, ctx):
        args = ctx.get_args("ascii")
        if len(args) == 0 or args[0].strip() == "":
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} Please specify a timezone to link.")

        tz = args[0].lower().strip()
        lower_timezones = list(map(str.lower, all_timezones))
        if tz not in lower_timezones:
            if tz.upper() in self.tz_abbreviations:
                tz = self.tz_abbreviations[tz.upper()][0]
            else:
                return await self.send_message(
                    ctx.channel,
                    f"@{ctx.user.display_name} That's not a valid timezone. "
                    "For setting the tz by UTC or GMT, as an example: UTC+5 would be Etc/GMT-5. "
                    "Do !validtz if you are having trouble."
                )
        else:
            tz = all_timezones[lower_timezones.index(tz)]

        await self.db.set_timezone(ctx.user_id, ctx.sending_user, tz)
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} Timezone has been linked!")

    @command_manager.command(
        "utime",
        "Check what time it is for another user or yourself. They must have a timezone linked via !linktz.",
        [
            CommandArg("user", "username of user to get time for, or empty for yourself", is_optional=True)
        ],
        aliases=["usertime"],
        cooldown=Cooldown(1, 1)
    )
    async def user_time(self, ctx):
        args = ctx.get_args("ascii")
        if len(args) == 0 or args[0].strip() == "":
            username = ctx.user.username
        else:
            username = args[0].lower().replace("@", "")

        user = await self.db.get_user_if_exists(username)
        if user is None:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} {username} is not in the database"
            )

        tz = await self.db.get_user_timezone(user.id)
        if tz is None:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} {'This user has' if username != ctx.sending_user else 'You have'} "
                f"not linked a timezone, which can be done with !linktz"
            )

        tz = timezone(tz.timezone)
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} Time for {username}: "
            f"{datetime.now().astimezone(tz).strftime('%H:%M (%Z)')}"
        )
