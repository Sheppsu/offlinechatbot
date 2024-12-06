from .base import CommandBot, BotMeta
from ..context import ServerMessageContext


class ServerMessageHandlerBot(CommandBot, metaclass=BotMeta):
    async def on_server_msg(self, ctx: ServerMessageContext):
        await self.HANDLERS[ctx.data["cmd"]](self, ctx.data)

    async def on_refresh_channel(self, data):
        new_channel = await self.db.get_channel(data["channel_id"])

        for i, channel in enumerate(self.channels):
            if channel.id == data["channel_id"]:
                if not new_channel.is_enabled:
                    await self.part(channel.user.username)
                    self.offline_channels.pop(channel.user.username, None)
                    self.channels.pop(i)
                    return

                self.channels[i] = new_channel

                if new_channel.user.username != channel.user.username:
                    await self.part(channel.user.username)
                    await self.join(new_channel.user.username)
                    offline_value = self.offline_channels.pop(channel.user.username, None)
                    if offline_value is not None:
                        self.offline_channels[new_channel.user.username] = offline_value

                if new_channel.is_offline_only and not channel.is_offline_only:
                    self.offline_channels[new_channel.user.username] = False
                elif not new_channel.is_offline_only and channel.is_offline_only:
                    self.offline_channels.pop(new_channel.user.username, None)

                return

        if not new_channel.is_enabled:
            return

        # new channel
        self.channels.append(new_channel)
        await self.join(new_channel.user.username)

    HANDLERS = [on_refresh_channel]
