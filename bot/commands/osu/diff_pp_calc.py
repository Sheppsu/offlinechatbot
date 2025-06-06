from __future__ import annotations

import beatmap_reader as br
import rosu_pp_py as rosu
from collections import namedtuple
from aiohttp import ClientSession
import logging
import osu
import asyncio


log = logging.getLogger(__name__)


class BeatmapFileManager:
    __slots__ = ("_lock",)

    def __init__(self):
        self._lock = asyncio.Lock()

    async def get_beatmap_file(self, beatmap_id: int) -> bytes | None:
        async with self._lock:
            async with ClientSession() as session:
                async with session.get(f"https://osu.ppy.sh/osu/{beatmap_id}") as resp:
                    try:
                        resp.raise_for_status()
                    except Exception as e:
                        log.exception(f"Failed to get osu beatmap", exc_info=e)
                        return
                    return await resp.read()


class BeatmapReader(br.BeatmapReader):
    __slots__ = ("lines",)

    def __init__(self, lines):
        super().__init__("")
        self.lines = lines

    def load_beatmap_data(self):
        data = {}
        current_section = None
        for line in self.lines:
            line = line[:-1]
            ascii_line = "".join(filter(lambda char: char.isascii(), line))
            if line.strip() == "" or line.startswith("//"):
                continue
            if current_section is None and ascii_line.startswith("osu file format"):
                data.update({"version": int(ascii_line[17:].strip())})
                continue
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1]
                data.update({current_section: {} if current_section in self.key_value_sections else []})
                continue
            if current_section is None:
                continue
            if current_section in self.key_value_sections:
                kv = map(str.strip, line.split(":", 1))
                data[current_section].update({next(kv): next(kv)})
            else:
                data[current_section].append(line.strip())
        return data


LegacyStats = namedtuple("SimpleStats", ("n_geki", "n300", "n_katu", "n100", "n50", "misses"))


class BeatmapCalculator:
    __slots__ = ("beatmap", "info", "last_diff", "last_perf", "last_mods", "last_clock_rate", "last_lazer", "last_passed", "beatmap_id")

    beatmap_file_manager = BeatmapFileManager()

    def __init__(self, beatmap: rosu.Beatmap, info: br.Beatmap, beatmap_id: int):
        self.beatmap: rosu.Beatmap = beatmap
        self.info: br.Beatmap = info  # used by commands for displaying artist information n stuff
        self.last_diff: None | rosu.DifficultyAttributes = None
        self.last_perf: None | rosu.PerformanceAttributes = None
        self.last_mods: None | int = None
        self.last_clock_rate: None | float = None
        self.last_lazer: None | bool = None
        self.last_passed: None | bool = None
        self.beatmap_id = beatmap_id

    @classmethod
    async def from_beatmap_id(cls, beatmap_id: int) -> BeatmapCalculator | None:
        content = await cls.beatmap_file_manager.get_beatmap_file(beatmap_id)
        if content is None or len(content) == 0:
            return None

        info = br.Beatmap(BeatmapReader(content.decode("utf-8").split("\n")))
        info.load()
        return cls(rosu.Beatmap(bytes=content), info, beatmap_id)

    @staticmethod
    def parse_stats(stats: osu.ScoreDataStatistics) -> LegacyStats:
        values = (
            stats.perfect,
            stats.great,
            stats.good if stats.good is not None else stats.small_tick_miss,
            stats.ok if stats.ok is not None else stats.large_tick_hit,
            stats.meh,
            stats.miss,
        )
        return LegacyStats(*map(lambda h: h or 0, values))

    @staticmethod
    def hits_to_string(hits, ruleset_id) -> str:
        return "/".join(map(lambda i: str(hits[i]), {
            0: (1, 3, 4, 5),
            1: (1, 3, 5),
            2: (1, 4, 2, 5),
            3: (0, 1, 2, 3, 4, 5)
        }[ruleset_id]))

    @staticmethod
    def get_perf(stats: osu.ScoreDataStatistics, combo: int, mods: int, clock_rate: float, lazer: bool, passed: bool = True) -> tuple[rosu.Performance, LegacyStats]:
        legacy_stats = BeatmapCalculator.parse_stats(stats)
        perf = rosu.Performance(
            n300=legacy_stats.n300,
            n100=legacy_stats.n100,
            n50=legacy_stats.n50,
            misses=legacy_stats.misses,
            n_geki=legacy_stats.n_geki,
            n_katu=legacy_stats.n_katu,
            large_tick_hits=stats.large_tick_hit or 0,
            small_tick_hits=stats.small_tick_hit or 0,
            slider_end_hits=stats.slider_tail_hit or 0,
            combo=combo,
            mods=mods,
            clock_rate=clock_rate,
            lazer=lazer
        )
        if not passed:
            perf.set_passed_objects(sum(legacy_stats))
        return perf, legacy_stats

    @staticmethod
    def get_score_settings(score: osu.SoloScore) -> tuple[int, float, bool]:
        mods = 0
        lazer = True
        for mod in score.mods:
            if mod.mod == osu.Mod.Classic:
                lazer = False

            try:
                mods += osu.Mods[mod.mod.name].value
            except (AttributeError, KeyError):
                continue

        for mod in score.mods:
            if mod.settings is not None and "speed_change" in mod.settings:
                return mods, mod.settings["speed_change"], lazer
            if mod.mod == osu.Mod.DoubleTime or mod.mod == osu.Mod.Nightcore:
                return mods, 1.5, lazer
            if mod.mod == osu.Mod.HalfTime or mod.mod == osu.Mod.Daycore:
                return mods, 0.75, lazer

        return mods, 1.0, lazer

    @staticmethod
    def calc_acc(stats, ruleset_id) -> float:
        if isinstance(stats, osu.ScoreDataStatistics):
            stats = BeatmapCalculator.parse_stats(stats)
        return {
            0: lambda s: (300 * s.n300 + 100 * s.n100 + 50 * s.n50) / (300 * (s.n300 + s.n100 + s.n50 + s.misses)),
            1: lambda s: (s.n300 + 0.5 * s.n_katu) / (s.n300 + s.n_katu + s.misses),
            2: lambda s: (s.n300 + s.n100 + s.n50) / (s.miss + s.n_katu + s.n300 + s.n100 + s.n50),
            3: lambda s: (300 * (s.n_geki + s.n300) + 200 * s.n_katu + 100 * s.n100 + 50 * s.n50) / (300 * (s.n_geki + s.n300 + s.n_katu + s.n100 + s.n50 + s.misses))
        }[ruleset_id](stats)

    def calculate_difficulty(self, mods: int, clock_rate: float | None = None) -> rosu.DifficultyAttributes:
        if clock_rate is None:
            clock_rate = 1.0
            if osu.Mods.DoubleTime.value & mods or osu.Mods.Nightcore.value & mods:
                clock_rate = 1.5
            elif osu.Mods.HalfTime.value & mods:
                clock_rate = 0.75
        self.last_diff = rosu.Difficulty(mods=mods, clock_rate=clock_rate).calculate(self.beatmap)
        self.last_mods = mods
        self.last_clock_rate = clock_rate
        return self.last_diff

    def calculate(self, score: osu.SoloScore) -> tuple[rosu.PerformanceAttributes, LegacyStats]:
        mods, clock_rate, lazer = self.get_score_settings(score)
        perf, stats = self.get_perf(score.statistics, score.max_combo, mods, clock_rate, lazer, score.passed)
        self.last_perf = perf.calculate(
            self.beatmap if self.last_mods != mods or self.last_clock_rate != clock_rate or self.last_lazer != lazer or
            not score.passed or not self.last_passed else self.last_diff
        )
        self.last_diff = self.last_perf.difficulty
        self.last_mods = mods
        self.last_clock_rate = clock_rate
        self.last_lazer = lazer
        self.last_passed = score.passed
        return self.last_perf, stats

    def calculate_if_fc(self, score: osu.SoloScore) -> tuple[rosu.PerformanceAttributes, float]:
        mods, clock_rate, lazer = self.get_score_settings(score)

        diff = self.calculate_difficulty(mods, clock_rate) if self.last_diff is None or self.last_mods != mods \
            or self.last_clock_rate != clock_rate or not score.passed or not self.last_passed else self.last_diff

        stats = self.parse_stats(score.statistics)
        stats = LegacyStats(
            stats.n_geki,
            stats.n300 + stats.misses if score.passed else
            stats.n300 + stats.misses + self.beatmap.n_objects - sum(stats),
            stats.n_katu,
            stats.n100,
            stats.n50,
            0,
        )
        perf = rosu.Performance(
            n300=stats.n300,
            n100=stats.n100,
            n50=stats.n50,
            misses=stats.misses,
            n_geki=stats.n_geki,
            n_katu=stats.n_katu,
            combo=diff.max_combo,
            mods=mods,
            clock_rate=clock_rate
        )

        self.last_perf = perf.calculate(diff)
        self.last_diff = diff
        self.last_mods = mods
        self.last_clock_rate = clock_rate
        self.last_passed = score.passed

        return (
            self.last_perf,
            self.calc_acc(stats, score.ruleset_id)
        )

    def calculate_from_acc(self, acc: float) -> rosu.PerformanceAttributes:
        if self.last_diff is None:
            self.calculate_difficulty(0, 1.0)

        return rosu.Performance(
            accuracy=acc*100,
            mods=self.last_mods,
            clock_rate=self.last_clock_rate
        ).calculate(self.last_diff)
