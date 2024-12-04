from .static_data import StaticDataBot
from .base import Cooldown
from ..context import MessageContext
from ..bot import BotMeta
from ..database import Database, AnimeCompareGame

import random
import asyncio


# class AnimeCompareGame:
#     def __init__(self, user, answers, score=0):
#         self.id = None
#         self.user = user
#         self.answers = answers
#         self.score = score
#         self.finished = False
#
#     @property
#     def answer(self):
#         return 1 if self.answers["anime1"][1] < self.answers["anime2"][1] else 2
#
#     def get_question_string(self):
#         return f"Which anime is more popular? {self.answers['anime1'][0]} or {self.answers['anime2'][0]}"
#
#     def get_ranking_string(self):
#         return f"Popularity ranking: {self.answers['anime1'][0]} - #{self.answers['anime1'][1]+1} | {self.answers['anime2'][0]} - #{self.answers['anime2'][1]+1}"
#
#
# class AnimeCompare:
#     def __init__(self):
#         self.current_games = []
#
#     def generate_answer(self, anime_list) -> dict[str, tuple[str, int]]:
#         anime1_i = random.randint(0, len(anime_list)-1)
#         anime1 = anime_list.pop(anime1_i)
#         anime2_i = random.randint(0, len(anime_list)-1)
#         anime2 = anime_list.pop(anime2_i)
#         anime_list.insert(anime1_i, anime1)
#
#         return {
#             "anime1": (anime1, anime1_i),
#             "anime2": (anime2, anime2_i + (1 if anime2_i >= anime1_i else 0))
#         }
#
#     def new_game(self, user, anime_list) -> AnimeCompareGame:
#         game = AnimeCompareGame(user, self.generate_answer(anime_list))
#         self.current_games.append(game)
#         return game
#
#     @staticmethod
#     def check_guess(ctx, game):
#         guess = ctx.message
#         guess = "".join([char for char in guess if char.isascii()]).strip()  # Remove invis character from chatterino
#         if not guess.isdigit() or int(guess) not in [1, 2]:
#             return
#
#         if int(guess) == game.answer:
#             game.score += 1
#             return True
#         return False
#
#     def get_game(self, user) -> AnimeCompareGame:
#         for game in self.current_games:
#             if game.user == user:
#                 return game
#
#     def finish_game(self, game):
#         game.finished = True
#         index = -1
#         for i, cgame in enumerate(self.current_games):
#             if cgame.id == game.id:
#                 index = i
#                 break
#         if index != -1:
#             self.current_games.pop(index)
#
#     def __contains__(self, user):
#         return self.get_game(user) is not None


class Anime:
    __slots__ = ("title", "rank")

    def __init__(self, title, rank):
        self.title: str = title
        self.rank: int = rank


class AnimeCompareGameWrapper:
    __slots__ = ("data", "anime", "anime1", "anime2")

    def __init__(self, data: AnimeCompareGame, anime: list[str]):
        self.data = data
        self.anime = anime

        self.anime1: Anime = None  # type: ignore
        self.anime2: Anime = None  # type: ignore
        self.generate_answer()

    def generate_answer(self):
        anime1 = random.choice(self.anime)
        anime2 = random.choice(self.anime)
        while anime2 == anime1:
            anime2 = random.choice(self.anime)

        self.anime1 = Anime(anime1, self.anime.index(anime1)+1)
        self.anime2 = Anime(anime2, self.anime.index(anime2)+1)

    def get_question_string(self):
        return f"Which anime is more popular? [1] {self.anime1.title} or [2] {self.anime2.title}"

    def get_answer_string(self):
        return f"[#{self.anime1.rank}] {self.anime1.title} vs [#{self.anime2.rank}] {self.anime2.title}]"

    def is_right_answer(self, num: int):
        return num == (2 if self.anime1.rank > self.anime2.rank else 1)

    def increment_local_score(self):
        self.data = AnimeCompareGame(
            self.data.id,
            self.data.score + 1,
            self.data.is_finished,
            self.data.user
        )


class AnimeCompare:
    __slots__ = ("db", "games", "anime")

    def __init__(self, db: Database, anime: list[str]):
        self.db: Database = db
        self.games: list[AnimeCompareGameWrapper] = []
        self.anime: list[str] = anime

    async def setup(self):
        self.games = list((
            AnimeCompareGameWrapper(game, self.anime)
            for game in await self.db.get_in_progress_ac_games()
        ))

    def get_game(self, user_id: int) -> AnimeCompareGameWrapper | None:
        return next((game for game in self.games if game.data.user.id == user_id), None)

    def take_game(self, user_id: int) -> AnimeCompareGameWrapper | None:
        for i, game in enumerate(self.games):
            if game.data.user.id == user_id:
                return self.games.pop(i)

    def return_game(self, game: AnimeCompareGameWrapper):
        self.games.append(game)

    async def new_game(self, ctx: MessageContext) -> AnimeCompareGameWrapper:
        game = await self.db.start_ac_game(ctx.user_id, ctx.sending_user)
        self.games.append(game := AnimeCompareGameWrapper(game, self.anime))
        return game

    async def update_game(self, game: AnimeCompareGameWrapper, answer: int | None) -> tuple[str, bool]:
        is_right = False if answer is None else game.is_right_answer(answer)
        if is_right:
            await self.db.update_ac_game(game.data.id, game.data.score+1)
            game.increment_local_score()

            ret = (
                f"✅ Correct! {game.get_answer_string()} | Current score: {game.data.score}",
                True
            )
            game.generate_answer()
            return ret

        await self.db.finish_ac_game(game.data.id)
        return (
            f"❌ Incorrect. {game.get_answer_string()} | Final score: {game.data.score}",
            False
        )


class AnimeCompareBot(StaticDataBot, metaclass=BotMeta):
    command_manager = StaticDataBot.command_manager

    def __init__(self):
        self.helper: AnimeCompare = AnimeCompare(self.db, self.anime)
        self.futures: dict[int, asyncio.Future] = {}

    async def on_message(self, ctx: MessageContext):
        num = ctx.message[0]
        if num != "1" and num != "2":
            return

        game = self.helper.take_game(ctx.user_id)
        if game is None:
            return

        self.futures.pop(ctx.user_id).cancel()

        msg, is_right = await self.helper.update_game(game, int(num))
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} "+msg)

        if not is_right:
            return

        self.helper.return_game(game)

        await self.send_round(ctx, game)

    async def send_round(self, ctx: MessageContext, game: AnimeCompareGameWrapper):
        await self.send_message(ctx.channel, f"@{ctx.user.display_name} {game.get_question_string()}")

        self.futures[ctx.user_id] = self.call_later(10, self.anime_compare_timeout, ctx)

    @command_manager.command(
        "anime_compare",
        "Play a game of deciding which anime is more popular (according to MAL).",
        aliases=["animecompare", "ac"],
        cooldown=Cooldown(0, 5)
    )
    async def anime_compare(self, ctx: MessageContext):
        game = self.helper.get_game(ctx.user_id)
        if game is not None:
            return

        game = await self.helper.new_game(ctx)
        game.generate_answer()

        await self.send_round(ctx, game)

    async def anime_compare_timeout(self, ctx: MessageContext):
        game = self.helper.take_game(ctx.user_id)
        if game is None:
            return

        await self.helper.update_game(game, None)
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} ❌ You did not answer in time. "
            f"{game.get_answer_string()} | Final score: {game.data.score}"
        )

        self.futures.pop(ctx.user_id)

    @command_manager.command(
        "average_ac",
        "See your average score from your anime compare games.",
        aliases=["acaverage", "ac_avg", "ac_average", "acavg"]
    )
    async def average_anime_compare(self, ctx: MessageContext):
        avg_score = await self.db.get_user_ac_avg(ctx.user_id)

        if avg_score is None:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} You have not played any anime compare games"
            )

        await self.send_message(ctx.channel, f"@{ctx.user.display_name} Your average score is {avg_score}.")

    @command_manager.command(
        "ac_leaderboard",
        "See the leaderboard of top 5 highest anime compare scores.",
        aliases=["aclb", "ac_lb", "acleaderboard"]
    )
    async def anime_compare_leaderboard(self, ctx: MessageContext):
        games = await self.db.get_top_ac_games()

        if games is None:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} No ac games have been played yet"
            )

        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} The top anime compare scores are: "
            f"{', '.join(['%s_%d' % (game.user.username, game.score) for game in games])}."
        )

    @command_manager.command(
        "ac_top",
        "See your best anime compare score.",
        aliases=["actop", "topac", "top_ac"],
        cooldown=Cooldown(0, 5)
    )
    async def anime_compare_top(self, ctx: MessageContext):
        games = await self.db.get_top_ac_games_for_user(ctx.user_id)

        if games is None:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} You have not played any anime compare games yet."
            )

        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} Your top anime compare score is {games[0].score}."
        )
