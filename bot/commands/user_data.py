from .base import CommandBot, Cooldown, CommandArg
from ..context import MessageContext
from ..bot import BotMeta


class UserDataBot(CommandBot, metaclass=BotMeta):
    command_manager = CommandBot.command_manager

    @command_manager.command(
        "bal",
        "Check the balance of yourself or a user",
        [
            CommandArg("user", "username of the user to check, or empty if yourself", is_optional=True)
        ],
        aliases=["balance"]
    )
    async def balance(self, ctx: MessageContext):
        args = ctx.get_args()
        user_to_check = args[0].replace("@", "").lower() if args else None
        if user_to_check is None:
            user = await self.db.get_user(ctx.user_id, ctx.sending_user)
        else:
            user = await self.db.get_user_if_exists(user_to_check)

        await self.send_message(
            ctx.channel,
            f"{user.username} currently has {user.money} Becky Bucks."
        )

    @command_manager.command(
        "leaderboard",
        "Check the leaderboard for becky bucks",
        aliases=["lb"]
    )
    async def leaderboard(self, ctx: MessageContext):
        top_users = await self.db.get_top_users()
        await self.send_message(
            ctx.channel,
            "Top 5 richest users: " + " ".join((
                f'{i + 1}. {user.username}_${user.money}'
                for i, user in enumerate(top_users)
            ))
        )

    @command_manager.command(
        "ranking",
        "Check your ranking on the becky bucks leaderboard"
    )
    async def get_ranking(self, ctx: MessageContext):
        rank = await self.db.get_user_ranking(ctx)
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} You are currently rank {rank} in terms of Becky Bucks!"
        )

    @command_manager.command(
        "give",
        "Give becky bucks to another user. They must have their can_receive_money setting turned on.",
        [
            CommandArg("user", "username of user to give becky bucks to"),
            CommandArg("amount", "amount of becky bucks to give")
        ]
    )
    async def give(self, ctx: MessageContext):
        args = ctx.get_args()
        if len(args) < 2:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Must say the user and amount of money to give"
            )

        user_to_give = args[0].lower()
        user = await self.db.get_user_if_exists(user_to_give)
        if user is None:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} That user does not exist in the database"
            )

        if not user.can_receive_money:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} This user has their receive setting "
                "turned off and therefore cannot accept money."
            )

        amount = args[1]
        try:
            amount = round(int(amount))
        except ValueError:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} That's not a valid number.")

        if amount < 0:
            return await self.send_message(ctx.channel, "You can't give someone a negative amount OuttaPocket Tssk")

        giving_user = await self.db.get_user(ctx.user_id, ctx.sending_user)
        if giving_user.money < amount:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} You too broke for that bruh 😭😭"
            )

        await self.db.add_money(ctx.user_id, ctx.sending_user, -amount)
        await self.db.add_money(user.id, user.username, amount)
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} You have given {user.username} {amount} Becky Bucks!"
        )
