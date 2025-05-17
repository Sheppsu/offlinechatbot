from ..base import Cooldown, CommandArg
from ...context import JoinContext
from .diff_pp_calc import BeatmapCalculator
from ...util import format_date
from ...bot import BotMeta
from .client import OsuClientBot

from osu import Mod, SoloScore, GameModeStr, GameModeInt, Mods
from aiohttp import client_exceptions, ClientSession
from datetime import datetime
import logging
import json
import asyncio
import rosu_pp_py as rosu
import random


proper_mode_name = {
    "osu": "osu!standard",
    "taiko": "osu!taiko",
    "fruits": "osu!catch",
    "mania": "osu!mania"
}
log = logging.getLogger(__name__)


class OsuBot(OsuClientBot, metaclass=BotMeta):
    __slots__ = ("osu_user_id_cache", "recent_score_cache", "max_medals")

    command_manager = OsuClientBot.command_manager

    def __init__(self):
        self.osu_user_id_cache = {}
        self.recent_score_cache = {}

    async def on_setup(self, ctx):
        self.max_medals = await self.get_max_medals()

    async def on_join(self, ctx: JoinContext):
        self.recent_score_cache[ctx.channel] = {}

    async def get_max_medals(self):
        try:
            async with ClientSession() as session:
                async with session.get("https://inex.osekai.net/api/medals/get_all") as resp:
                    return len(json.loads(await resp.read()).get("content", []))
        except Exception as exc:
            log.exception("Unable to fetch total medals from osekai", exc_info=exc)
            return 0

    async def process_osu_user_arg(self, ctx, args):
        if len(args) > 0:
            return " ".join(args).strip()

        osu_user = await self.db.get_osu_from_id(ctx.user_id)
        if osu_user is not None:
            print(osu_user)
            self.osu_user_id_cache[osu_user.osu.username] = osu_user.osu.id
            return osu_user.osu.id

        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} Please specify a username or link your account with !link [username]."
        )

    async def process_osu_mode_args(self, ctx, args, required=True, as_int=False) -> int | str:
        arg = self.process_value_arg("-m", args, 0)
        if arg is None and required:
            await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Must specify a mode with the -m argument. "
                "Valid modes are 0 (osu), 1 (taiko), 2 (catch), 3 (mania)."
            )
            return
        elif not required:
            return -1
        if isinstance(arg, str) and (not arg.isdigit() or int(arg) not in range(0, 4)):
            await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Invalid mode. Valid modes "
                "are 0 (osu), 1 (taiko), 2 (catch), 3 (mania)."
            )
            return
        return int(arg) if as_int else ("osu", "taiko", "fruits", "mania")[int(arg)]

    async def get_osu_user_id_from_osu_username(self, ctx, username):
        if username not in self.osu_user_id_cache:
            user = await self.osu_client.get_user(user=username, key="username")
            if user is None:
                await self.send_message(ctx.channel, f"@{ctx.user.display_name} User {username} not found.")
                return
            self.osu_user_id_cache[username] = user.id
        return self.osu_user_id_cache[username]

    @staticmethod
    def get_mod_string(mods):
        def fmt_settings(m):
            if m.settings is None:
                return ""

            if "speed_change" in m.settings:
                return f"({round(m.settings['speed_change'], 2)}x)"

            if Mod.DifficultyAdjust == m.mod:
                return f"({'|'.join((''.join(map(lambda s: s[0], k.upper().split('_'))) + f'={v}' for k, v in m.settings.items()))})"

            return ""

        return "".join(map(
            lambda m: m.mod.value + fmt_settings(m),
            mods
        ))

    def get_score_attrs(self, calc, score):
        perf = calc.calculate(score)
        fc_perf, fc_acc = calc.calculate_if_fc(score) if (
                (perf.effective_miss_count is not None and perf.effective_miss_count >= 1) or
                not score.passed or
                (score.statistics.miss is not None and score.statistics.miss > 0)
        ) else (None, None)
        hits = BeatmapCalculator.parse_stats(score.statistics)
        return perf, fc_perf, fc_acc, hits

    async def get_score_message(self, score: SoloScore, prefix="Recent score for {username}") -> tuple[
        str, BeatmapCalculator]:
        score_format = prefix + ":{passed} {artist} - {title} [{diff}]{mods} ({mapper}, {star_rating}*) " \
                                "{acc}% {combo}/{max_combo} | ({hit_counts}) | {pp}{if_fc_pp} | {time_ago} ago"

        calc = await BeatmapCalculator.from_beatmap_id(score.beatmap_id)
        perf, fc_perf, fc_acc, hits = self.get_score_attrs(calc, score)

        pp = score.pp or perf.pp

        bm_perf = fc_perf if not score.passed else perf

        return score_format.format(**{
            "username": score.user.username,
            "passed": "" if score.passed else f" (Failed {round(sum(hits) / calc.beatmap.n_objects * 100)}%)",
            "artist": calc.info.metadata.artist,
            "title": calc.info.metadata.title,
            "diff": calc.info.metadata.version,
            "mods": " +" + self.get_mod_string(score.mods) if score.mods else "",
            "mapper": calc.info.metadata.creator,
            "star_rating": round(bm_perf.difficulty.stars, 2),
            "pp": f"{round(pp, 2)}pp",
            "if_fc_pp": f" ({round(fc_perf.pp, 2)} for {round(fc_acc * 100, 2)}% FC)" if fc_perf is not None else "",
            "acc": round(score.accuracy * 100, 2),
            "combo": score.max_combo,
            "max_combo": bm_perf.difficulty.max_combo,
            "hit_counts": BeatmapCalculator.hits_to_string(hits, score.ruleset_id),
            "time_ago": format_date(score.ended_at)
        }), calc

    async def get_compact_scores_message(self, scores) -> str:
        score_format = "{artist} - {title} [{diff}]{mods} ({sr}*) {acc}% ({hit_counts}): {pp}pp{fc_pp} | {time_ago} ago"
        message = ""
        calcs: tuple[BeatmapCalculator] = await asyncio.gather(
            *(BeatmapCalculator.from_beatmap_id(score.beatmap_id) for score in scores)
        )
        for calc, score in zip(calcs, scores):
            perf, fc_perf, fc_acc, hits = self.get_score_attrs(calc, score)

            message += "🌟" + score_format.format(**{
                "artist": calc.info.metadata.artist,
                "title": calc.info.metadata.title,
                "diff": calc.info.metadata.version,
                "mods": " +" + self.get_mod_string(score.mods) if score.mods else "",
                "sr": round((perf if score.passed else fc_perf).difficulty.stars, 2),
                "acc": round(score.accuracy * 100, 2),
                "hit_counts": BeatmapCalculator.hits_to_string(hits, score.ruleset_id),
                "pp": round(perf.pp, 2),
                "fc_pp": f" ({round(fc_perf.pp, 2)} for {round(fc_acc * 100, 2)}% FC)" if fc_perf is not None else "",
                "time_ago": format_date(score.ended_at),
            })
        return message

    async def get_osu_user_id_from_args(self, ctx, args) -> int | None:
        user = await self.process_osu_user_arg(ctx, args)
        if user is None:
            return
        if isinstance(user, str):
            return await self.get_osu_user_id_from_osu_username(ctx, user)
        return user

    def osu_username_from_id(self, user_id):
        for username, osu_user_id in self.osu_user_id_cache.items():
            if osu_user_id == user_id:
                return username

    def get_map_cache(self, ctx) -> BeatmapCalculator | None:
        if len(self.recent_score_cache[ctx.channel]) == 0:
            return
        if ctx.reply:
            if ctx.reply.msg_body in self.recent_score_cache[ctx.channel]:
                return self.recent_score_cache[ctx.channel][ctx.reply.msg_body]
            return
        return tuple(self.recent_score_cache[ctx.channel].values())[-1]

    def add_recent_map(self, ctx, sent_message, bm_calc):
        msg = " ".join(sent_message)
        if msg in self.recent_score_cache[ctx.channel]:
            del self.recent_score_cache[ctx.channel][msg]
        self.recent_score_cache[ctx.channel].update({msg: bm_calc})
        while len(self.recent_score_cache[ctx.channel]) > 10:
            del self.recent_score_cache[ctx.channel][next(iter(self.recent_score_cache[ctx.channel].keys()))]

    async def get_beatmap_from_arg(self, ctx, beatmap_link):
        beatmap_id = tuple(filter(lambda s: len(s.strip()) > 0, beatmap_link.split("/")))[-1]
        calc = await BeatmapCalculator.from_beatmap_id(beatmap_id)
        if calc is None:
            return await self.send_message(ctx.channel, "Failed to get beatmap from the provided link/id.")
        return calc

    @command_manager.command(
        "rs",
        "Get recent osu score for you or a user",
        [
            CommandArg(
                "username",
                "osu username to get recent score for, or empty for yourself",
                is_optional=True
            ),
            CommandArg(
                "mode",
                "osu gamemode to use: 0 (osu), 1 (taiko), 2 (catch), 3 (mania)",
                is_optional=True,
                flag="m"
            ),
            CommandArg(
                "index",
                is_optional=True,
                flag="i"
            ),
            CommandArg(
                "",
                "get most recent score in the user's top 100 scores",
                is_optional=True,
                flag="b"
            )
        ],
        cooldown=Cooldown(0, 3)
    )
    async def recent_score(self, ctx):
        args = ctx.get_args('ascii')
        mode = await self.process_osu_mode_args(ctx, args)
        if mode is None:
            return
        index = await self.process_index_arg(ctx, args)
        if index is None:
            return
        if index == -1:
            index = 0
        best = self.process_arg("-b", args)

        user_id = await self.get_osu_user_id_from_args(ctx, args)
        if user_id is None:
            return
        username = self.osu_username_from_id(user_id)

        # Get recent score
        if not best:
            scores = await self.osu_client.get_user_scores(
                user_id, "recent", include_fails=1, mode=mode, limit=1, offset=index
            )
        else:
            scores = await self.osu_client.get_user_scores(user_id, "best", mode=mode, limit=100)
            scores = sorted(scores, key=lambda x: x.ended_at, reverse=True)
        if not scores:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} User {username} "
                                                        f"has no recent scores for {proper_mode_name[mode]} "
                                                        "or the index you specified is out of range.")

        score = scores[0 if not best else index]
        msg, calc = await self.get_score_message(score)
        sent_message = await self.send_message(ctx.channel, msg)
        self.add_recent_map(ctx, sent_message, calc)

    @command_manager.command(
        "c",
        "Compare scores on a map. Map depends on last osu command used. Can also reply to a response to specify a map.",
        [
            CommandArg("username", "osu user to get scores for, or yourself if empty", is_optional=True)
        ],
        aliases=['compare'],
        cooldown=Cooldown(0, 3)
    )
    async def compare_score(self, ctx):
        if not len(self.recent_score_cache[ctx.channel]):
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} I don't have a cache of the last beatmap."
            )
        cache = self.get_map_cache(ctx)
        if cache is None:
            return
        await self.compare_score_func(ctx, cache)

    async def compare_score_func(self, ctx, cache=None):
        calc = self.get_map_cache(ctx) if cache is None else cache
        if calc is None:
            return

        args = ctx.get_args('ascii')
        mode = await self.process_osu_mode_args(ctx, args, required=False, as_int=True)
        if mode is None:
            return
        elif mode == -1:
            mode = int(calc.beatmap.mode)

        user_id = await self.get_osu_user_id_from_args(ctx, args)
        if user_id is None:
            return
        username = self.osu_username_from_id(user_id)

        if mode != int(calc.beatmap.mode):
            calc.beatmap.convert(rosu.GameMode(mode))

        mode = GameModeStr[GameModeInt(mode).name].value

        try:
            scores = await self.osu_client.get_user_beatmap_scores(calc.beatmap_id, user_id, mode)
        except client_exceptions.ClientResponseError:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Either this map does not have a leaderboard or "
                "an unexpected error occurred"
            )
        if not scores:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} User {username} has no "
                f"scores on that beatmap for mode {proper_mode_name[mode]}."
            )

        score_format = "{mods} {acc}% {combo}/{max_combo} | ({hit_counts}) | {pp} | {time_ago} ago"
        message = f"Scores for {username} on {calc.info.metadata.artist} - {calc.info.metadata.title} " \
                  f"[{calc.info.metadata.version}] ({calc.info.metadata.creator}): "
        for score in scores[:5]:
            perf = calc.calculate(score)
            hits = calc.parse_stats(score.statistics)
            message += "🌟" + score_format.format(**{
                "mods": " +" + "".join(map(lambda m: m.mod.value, score.mods)) if score.mods else "",
                "acc": round(score.accuracy * 100, 2),
                "combo": score.max_combo,
                "max_combo": perf.difficulty.max_combo,
                "hit_counts": BeatmapCalculator.hits_to_string(hits, score.ruleset_id),
                "pp": f"{round(perf.pp, 2)}pp",
                "time_ago": format_date(score.ended_at)
            })
        sent_message = await self.send_message(ctx.channel, message)
        self.add_recent_map(ctx, sent_message, calc)

    async def get_beatmap_from_arg_or_cache(self, ctx, args):
        if len(args) > 0:
            return await self.get_beatmap_from_arg(ctx, args[0])
        elif len(self.recent_score_cache[ctx.channel]) == 0:
            await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} I don't have a cache of the last beatmap."
            )
        else:
            return self.get_map_cache(ctx)

    @command_manager.command(
        "map",
        "Send link and stats of a map. Specify id or let it use map from last osu command.",
        [
            CommandArg("beatmap id", is_optional=True)
        ],
        aliases=["m"]
    )
    async def send_map(self, ctx):
        args = ctx.get_args('ascii')

        calc = await self.get_beatmap_from_arg_or_cache(ctx, args)
        if calc is None:
            return

        diff = rosu.Difficulty().calculate(calc.beatmap)
        text = (
            f"{calc.info.metadata.artist} - {calc.info.metadata.title} [{calc.info.metadata.version}] "
            f"({calc.info.metadata.creator}, {round(diff.stars, 2)}*) "
            f"https://osu.ppy.sh/b/{calc.beatmap_id}"
        )
        sent_message = await self.send_message(ctx.channel, f"@{ctx.user.display_name} {text}")
        self.add_recent_map(ctx, sent_message, calc)

    @command_manager.command(
        "osu",
        "Send osu profile of a user",
        [
            CommandArg("username", "osu username or yourself if empty", is_optional=True),
            CommandArg(
                "mode",
                "osu gamemode to use: 0 (osu), 1 (taiko), 2 (catch), 3 (mania)",
                is_optional=True,
                flag="m"
            ),
        ],
        aliases=["profile", "o"],
        cooldown=Cooldown(0, 5)
    )
    async def osu_profile(self, ctx):
        args = ctx.get_args('ascii')

        mode = await self.process_osu_mode_args(ctx, args)
        if mode is None:
            return

        user = await self.get_osu_user_id_from_args(ctx, args)
        if user is None:
            return

        username = self.osu_username_from_id(user)

        try:
            user = await self.osu_client.get_user(user=user, mode=mode)
        except client_exceptions.ClientResponseError:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Failed to get user. "
                "Either the osu api is borked or the user does not exist or is restricted."
            )

        if user is None:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} User {username} not found.")

        stats = user.statistics
        if (rank_history := user.rank_history) is not None:
            rank_history = user.rank_history.data
            rank_direction = rank_history[min(len(rank_history), 29)] - rank_history[-1]
            rank_direction = ("↑" if rank_direction >= 0 else "↓") + str(abs(rank_direction))

        profile_layout = (
            "{username}'s profile [{mode}]: #{global_rank}{rank_direction} ({country}#{country_rank}) - "
            "{pp}pp; Peak: #{peak_rank} {peak_time_ago} ago | {accuracy}% | {play_count} playcount "
            "({play_time} hrs) | Medal count: {medal_count}/{total_medals} ({medal_completion}%) | "
            "Followers: {follower_count} | Mapping subs: {subscriber_count}"
        )
        await self.send_message(ctx.channel, profile_layout.format(**{
            "username": user.username,
            "mode": proper_mode_name[mode],
            "rank_direction": " " + rank_direction if rank_history is not None else "",
            "global_rank": stats.global_rank,
            "country": user.country.code,
            "country_rank": stats.country_rank,
            "pp": stats.pp,
            "peak_rank": user.rank_highest.rank,
            "peak_time_ago": format_date(user.rank_highest.updated_at),
            "accuracy": round(stats.hit_accuracy, 2),
            "play_count": stats.play_count,
            "play_time": stats.play_time // 3600,
            "medal_count": len(user.user_achievements),
            "total_medals": self.max_medals,
            "medal_completion": 0 if self.max_medals == 0 else round(
                len(user.user_achievements) / self.max_medals * 100, 2),
            "follower_count": user.follower_count,
            "subscriber_count": user.mapping_follower_count,
        }))

    @command_manager.command(
        "osutop",
        "List top 5 osu scores for a user",
        [
            CommandArg("username", "osu username or yourself if empty", is_optional=True),
            CommandArg(
                "mode",
                "osu gamemode to use: 0 (osu), 1 (taiko), 2 (catch), 3 (mania)",
                is_optional=True,
                flag="m"
            ),
            CommandArg(
                "index",
                is_optional=True,
                flag="i"
            ),
            CommandArg(
                "",
                "sorts by most recent scores in top 100 scores",
                is_optional=True,
                flag="r"
            )
        ],
        cooldown=Cooldown(0, 5)
    )
    async def osu_top(self, ctx):
        args = ctx.get_args('ascii')

        mode = await self.process_osu_mode_args(ctx, args)
        if mode is None:
            return
        recent_tops = self.process_arg("-r", args)
        index = await self.process_index_arg(ctx, args, rng=range(1, 201))
        if index is None:
            return

        user_id = await self.get_osu_user_id_from_args(ctx, args)
        if user_id is None:
            return
        username = self.osu_username_from_id(user_id)

        if index == -1 and not recent_tops:
            top_scores = await self.osu_client.get_user_scores(user_id, "best", mode=mode, limit=5)
        elif not recent_tops:
            top_scores = await self.osu_client.get_user_scores(user_id, "best", mode=mode, limit=1, offset=index)
        else:
            top_scores = await self.osu_client.get_user_scores(user_id, "best", mode=mode, limit=100)
            top_scores += await self.osu_client.get_user_scores(user_id, "best", mode=mode, limit=100, offset=100)
            top_scores = sorted(top_scores, key=lambda x: x.ended_at, reverse=True)
            if index != -1:
                top_scores = [top_scores[index]]
            else:
                top_scores = top_scores[:5]

        if not top_scores:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} User {username} has no top scores for {proper_mode_name[mode]}."
            )

        username = top_scores[0].user.username

        calc = None
        if len(top_scores) > 1:
            message = f"Top{' recent' if recent_tops else ''} {proper_mode_name[mode]} " \
                      f"scores for {username}: " if index == -1 else f"Top {index + 1}{' recent' if recent_tops else ''} " \
                                                                     f"{proper_mode_name[mode]} score for {username}: "
            message += await self.get_compact_scores_message(top_scores)
        else:
            score = top_scores[0]
            message, calc = await self.get_score_message(
                score, f"Top {index + 1}{' recent' if recent_tops else ''} score for {username}"
            )

        sent_message = await self.send_message(ctx.channel, message)
        if calc is not None:
            self.add_recent_map(ctx, sent_message, calc)

    @command_manager.command(
        "link",
        "Link osu account",
        [
            CommandArg("username", "osu username of account to link to")
        ],
        cooldown=Cooldown(0, 2)
    )
    async def link_osu_account(self, ctx):
        args = ctx.get_args('ascii')
        if len(args) == 0 or args[0].strip() == "":
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} Please specify a username.")

        username = " ".join(args).strip()
        osu_user = await self.osu_client.get_user(user=username, key="username")

        if osu_user is None:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} User {username} not found.")

        await self.db.set_osu_info(
            ctx.user_id,
            ctx.sending_user,
            osu_user.id,
            osu_user.username,
            osu_user.statistics.global_rank
        )
        self.osu_user_id_cache[osu_user.username] = osu_user.id
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} Linked {osu_user.username} to your account."
        )

    @command_manager.command(
        "simulate",
        "List some pp values of a map for certain mods",
        [
            CommandArg("mods", "mod combination to calculate pp for", is_optional=True),
        ],
        cooldown=Cooldown(0, 2),
        aliases=["s"]
    )
    async def simulate_score(self, ctx):
        if len(self.recent_score_cache[ctx.channel]) == 0:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} I don't have a cache of the last beatmap."
            )
        calc = self.get_map_cache(ctx)
        if calc is None:
            return

        args = ctx.get_args("ascii")
        if len(args) == 0:
            mods = None
        else:
            mods = args[0]
            if mods.startswith("+"):
                mods = mods[1:]
            mods = [mods[i * 2:i * 2 + 2] for i in range(len(mods) // 2)]
            try:
                mods = list(map(Mods.get_from_abbreviation, mods))
            except KeyError:
                return await self.send_message(
                    ctx.channel,
                    f"{ctx.user.display_name} The mod combination you gave is invalid."
                )
            mods = Mods.get_from_list(mods)

        calc.calculate_difficulty(0 if mods is None else mods.value)

        pp_values = []
        for acc in (1, 0.99, 0.98, 0.97, 0.96, 0.95):
            perf = calc.calculate_from_acc(acc)
            pp_values.append(f"{int(acc * 100)}% - {round(perf.pp, 2)}")

        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} {calc.info.metadata.artist} - "
            f"{calc.info.metadata.title} [{calc.info.metadata.version}] "
            f"{mods.to_readable_string() if mods is not None else 'NM'}: "
            f"{' | '.join(pp_values)}"
        )

    @command_manager.command(
        "score",
        "Get scores for a specified map and user",
        [
            CommandArg("beatmap id", "beatmap id or link"),
            CommandArg("username", "osu username or empty for yourself", is_optional=True)
        ],
        aliases=["sc"]
    )
    async def osu_score(self, ctx):
        args = ctx.get_args('ascii')

        if len(args) < 1:
            return await self.send_message(ctx.channel, "Must give a beatmap link or beatmap id.")
        calc = await self.get_beatmap_from_arg(ctx, args[0])
        if calc is None:
            return

        i = ctx.message.index(args[0])
        ctx.message = (ctx.message[:i] + ctx.message[i + len(args[0]) + 1:]).strip()

        await self.compare_score_func(ctx, calc)

    # TODO: fix this command
    # @command_manager.command("send_map", aliases=["sm"])
    # async def send_osu_map(self, ctx):
    #     return await self.send_message(
    #         ctx.channel,
    #         f"@{ctx.user.display_name} Sorry! This command is temporarily disabled."
    #     )
    #
    #     calc = self.get_map_cache(ctx)
    #     if calc is None:
    #         return
    #     osu_user = await self.db.get_osu_user_from_user_id(ctx.user_id)
    #     if osu_user is None:
    #         return await self.send_message(
    #             ctx.channel,
    #             f"@{ctx.user.display_name} You must have your osu account linked and verified to use this command. "
    #             "You can link and verify by logging in at https://bot.sheppsu.me and "
    #             "then going to https://bot.sheppsu.me/osuauth (will take a few minutes to update)"
    #         )
    #     if not int(osu_user[2]):
    #         return await self.send_message(
    #             ctx.channel,
    #             f"@{ctx.user.display_name} You must have a verified account link to use this command. "
    #             "Go to https://bot.sheppsu.me, login, and then go to https://bot.sheppsu.me/osuauth (will take a few minutes to update)"
    #         )
    #
    #     md = calc.info.metadata
    #     bms_title = f"{md.artist} - {md.title} [{md.version}] mapped by {md.creator}"
    #     await self.osu_client.create_new_pm(osu_user[0],
    #                                         f"(Automated bot message) [{bms_title}](https://osu.ppy.sh/b/{md.beatmap_id})",
    #                                         False)
    #     await self.send_message(ctx.channel, f"@{ctx.user.display_name} Sent the beatmap to your osu DMs!")

    @command_manager.command(
        "preview",
        "send link to https://preview.tryz.id.vn for beatmap",
        [
            CommandArg("beatmap id", "beatmap id or link or empty", is_optional=True),
        ],
        aliases=["p"]
    )
    async def send_osu_preview(self, ctx):
        args = ctx.get_args("ascii")
        calc = await self.get_beatmap_from_arg_or_cache(ctx, args)
        if calc is None:
            return

        md = calc.info.metadata
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} {md.artist} - {md.title} [{md.version}] "
            f"https://preview.tryz.id.vn/?b={calc.beatmap_id}"
        )

    @command_manager.command(
        "random_score",
        "Send a random score from all recent scores of all players",
        [
            CommandArg(
                "",
                "Indicate to get a random score from a user",
                is_optional=True,
                flag="user"
            ),
            CommandArg(
                "username",
                "Username of the user to get scores from if the -user flag is used. "
                "Defaults to you if not specified.",
                is_optional=True
            ),
            CommandArg(
                "mods",
                "Specify mods to filter scores",
                flag="mods",
                is_optional=True
            )
        ]
    )
    async def send_random_recent_score(self, ctx):
        args = ctx.get_args("ascii")

        if self.process_arg("-user", args):
            await self.send_random_score_for_user(ctx, args)
            return

        mode = await self.process_osu_mode_args(ctx, args)
        if mode is None:
            return

        result = await self.osu_client.get_all_scores(mode)
        score = random.choice(result.scores)
        score.user = await self.osu_client.get_user(score.user_id)

        score_msg, bm_calc = await self.get_score_message(score, "Random recent score from {username}")
        msg = await self.send_message(ctx.channel, score_msg)

        self.add_recent_map(ctx, msg, bm_calc)

    async def send_random_score_for_user(self, ctx, args):
        mods = self.process_value_arg("-mods", args)
        if mods is not None:
            mods = mods.upper()
            mods = [mods[i * 2:i * 2 + 2] for i in range(len(mods) // 2)]
            try:
                mods.remove("CL")
            except ValueError:
                pass

        user_id = await self.get_osu_user_id_from_args(ctx, args)
        if user_id is None:
            return
        username = self.osu_username_from_id(user_id)

        async with ClientSession() as session:
            async with session.get(f"https://api.kirino.sh/inspector/scores/user/{user_id}?approved=1,2,4") as resp:
                data = await resp.json()

        def without_cl(score_mods):
            return [mod for mod in score_mods if mod["acronym"] != "CL"]

        if mods is not None:
            # filter scores by mods specified (exact match), ignoring CL
            data = [
                score
                for score in data
                if len(score_mods := without_cl(score.get("mods", []))) == len(mods) and
                all((mod["acronym"] in mods for mod in score_mods))
            ]

        if len(data) == 0:
            await self.send_message(ctx.channel, f"@{ctx.user.display_name} No scores on score.kirino.sh")
            return

        score = random.choice(data)

        calc = await BeatmapCalculator.from_beatmap_id(score["beatmap"]["beatmap_id"])

        score_format = "Random score for {username}: {artist} - {title} [{diff}]{mods} ({mapper}, {star_rating}*) " \
                       "{acc}% {combo}/{max_combo} | ({hit_counts}) | {pp}pp | {time_ago} ago"
        msg = await self.send_message(
            ctx.channel,
            score_format.format(
                username=username,
                artist=score["beatmap"]["artist"],
                title=score["beatmap"]["title"],
                diff=score["beatmap"]["diffname"],
                mods=(" +" + "".join((mod["acronym"] for mod in mods))) if len(mods := score.get("mods", [])) > 0 else "",
                mapper=score["beatmap"]["creator"],
                star_rating=round(float(score["beatmap"]["difficulty_data"]["star_rating"]), 2),
                acc=score["accuracy"],
                combo=score["combo"],
                max_combo=score["beatmap"]["maxcombo"],
                hit_counts="%d/%d/%d/%d" % (
                    score["count300"], score["count100"], score["count50"], score["countmiss"]
                ),
                pp=round(float(score["pp"]), 2),
                time_ago=format_date(datetime.fromisoformat(score["date_played"]))
            )
        )

        self.add_recent_map(ctx, msg, calc)
