from .base import CommandBot
from ..bot import BotMeta


class HelpBot(CommandBot, metaclass=BotMeta):
    command_manager = CommandBot.command_manager

    @command_manager.command(
        "help",
        "Sends a link to this website",
        aliases=[
            "sheepp_commands",
            "sheep_commands",
            "sheepcommands",
            "sheeppcommands",
            "sheephelp",
            "sheepphelp",
            "sheep_help",
            "sheep_help"
        ]
    )
    async def help_command(self, ctx):
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} sheppsubot help (do !commands for StreamElements): https://bot.sheppsu.me/"
        )

    @command_manager.command(
        "sourcecode",
        "Sends a link to the bot's github: https://github.com/Sheppsu/offlinechatbot",
        aliases=["github", "sheepcode", "sheeppcode", "sheep_code", "sheepp_code"]
    )
    async def sourcecode(self, ctx):
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} https://github.com/Sheppsu/offlinechatbot")

    @command_manager.command(
        "oct",
        "Send a link to the offline chat tournament website: https://oct.sheppsu.me"
    )
    async def offlinechattournament(self, ctx):
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} Offline Chat Tournament "
            f"(osu! tournament for offline chat) https://oct.sheppsu.me"
        )
