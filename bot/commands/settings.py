from .base import CommandBot, CommandArg
from ..database import USER_SETTINGS
from ..bot import BotMeta


class SettingsBot(CommandBot, metaclass=BotMeta):
    command_manager = CommandBot.command_manager

    @command_manager.command(
        "toggle",
        f"Toggle user settings on or off.",
        [
            CommandArg("setting", f"Valid settings are {', '.join(USER_SETTINGS)}"),
            CommandArg("toggle", "'on' or 'off'")
        ]
    )
    async def toggle(self, ctx):
        args = ctx.get_args()
        if len(args) < 2:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} You must provide a setting name and either on or off"
            )

        setting = args[0].lower()
        if setting not in USER_SETTINGS:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} That's not a valid setting name. "
                f"The settings consist of the following: " +
                ", ".join(USER_SETTINGS)
            )

        try:
            value = {"on": "true", "off": "false"}[args[1].lower()]
        except KeyError:
            return await self.send_message(ctx.channel, "You must specify 'on' or 'off'")

        await self.db.update_user_setting(ctx.user_id, ctx.sending_user, setting, value)
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} The {setting} setting has been turned {args[1]}."
        )
