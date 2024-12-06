from .base import CommandBot, BotMeta
from ..context import ServerMessageContext


class ServerMessageHandlerBot(CommandBot, metaclass=BotMeta):
    async def on_server_msg(self, ctx: ServerMessageContext):
        await self.HANDLERS[ctx.data["cmd"]](self, ctx.data)

    async def on_refresh_channel(self, data):
        new_channel = await self.db.get_channel(data["channel_id"])

        for i, channel in enumerate(self.channels):
            if channel.id == data["channel_id"]:
                self.channels[i] = new_channel

                if new_channel.user.username != channel.user.username:
                    await self.part(channel.user.username)
                    await self.join(new_channel.user.username)

                return

        # new channel
        self.channels.append(new_channel)
        await self.join(new_channel.user.username)

    HANDLERS = [on_refresh_channel]
