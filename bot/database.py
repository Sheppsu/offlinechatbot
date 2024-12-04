from __future__ import annotations

from .util import matching_zip

from psycopg import AsyncConnection
from dataclasses import dataclass
from time import time
from typing import TYPE_CHECKING
import os
import json


if TYPE_CHECKING:
    from .commands.base import CallableCommand


def select_fields(*objs) -> tuple[list[slice], str]:
    fields = []
    indices = []
    i = 0
    for obj in objs:
        indices.append(slice(i, i+len(obj.Meta.FIELDS)))
        i += len(obj.Meta.FIELDS)
        fields.extend((obj.Meta.TABLE+"."+field for field in obj.Meta.FIELDS))

    return indices, ",".join(fields)


@dataclass
class User:
    id: int
    username: str
    money: int
    can_receive_money: bool
    auto_remove_afk: bool

    class Meta:
        TABLE = "main_user"
        FIELDS = ["id", "username", "money", "can_receive_money", "auto_remove_afk"]


@dataclass
class UserAfk:
    id: int
    msg: str
    timestamp: int
    user: User

    class Meta:
        TABLE = "main_userafk"
        FIELDS = ["id", "msg", "timestamp"]


@dataclass
class UserReminder:
    id: int
    remind_at: int
    message: str
    user: User
    channel: UserChannel

    class Meta:
        TABLE = "main_userreminder"
        FIELDS = ["id", "remind_at", "message"]


@dataclass
class AnimeCompareGame:
    id: int
    score: int
    is_finished: bool
    user: User

    class Meta:
        TABLE = "main_animecomparegame"
        FIELDS = ["id", "score", "is_finished"]


@dataclass
class UserOsuData:
    id: int
    username: str
    global_rank: int

    class Meta:
        TABLE = "main_userosudata"
        FIELDS = ["id", "username", "global_rank"]


@dataclass
class UserOsuConnection:
    id: int
    is_verified: bool
    osu: UserOsuData
    user: User

    class Meta:
        TABLE = "main_userosuconnection"
        FIELDS = ["id", "is_verified"]


@dataclass
class UserTimezone:
    id: int
    timezone: str
    user: User

    class Meta:
        TABLE = "main_usertimezone"
        FIELDS = ["id", "timezone"]


@dataclass
class UserLastFM:
    id: int
    username: str
    user: User

    class Meta:
        TABLE = "main_userlastfm"
        FIELDS = ["id", "username"]


@dataclass
class Command:
    id: int
    name: str

    class Meta:
        TABLE = "main_command"
        FIELDS = ["id", "name"]


@dataclass
class ChannelCommand:
    id: int
    is_enabled: bool
    command_id: int
    channel_id: int
    command: Command

    class Meta:
        TABLE = "main_channelcommand"
        FIELDS = ["id", "is_enabled", "command_id", "channel_id"]


@dataclass
class UserChannel:
    id: int
    is_offline_only: bool
    user: User
    commands: list[ChannelCommand]

    class Meta:
        TABLE = "main_userchannel"
        FIELDS = ["id", "is_offline_only"]


USER_SETTINGS = (
    "can_receive_money", "auto_remove_afk"
)


def sqlstr(s):
    return "'"+s.replace("'", "''")+"'"


def use_cursor(commit=False):
    if callable(commit):
        raise RuntimeError("you forgot the parenthesis after @use_cursor")

    def decorator(func):
        async def wrapper(self, *args, **kwargs):
            conn = await self.get_connection()
            async with conn.cursor() as cursor:
                result = await func(self, *args, **kwargs, cursor=cursor)

                if commit:
                    await conn.commit()

            await conn.close()

            return result

        return wrapper

    return decorator


class Database:
    CONNINFO = os.getenv("PGURL")

    def __init__(self):
        if self.CONNINFO is None:
            raise RuntimeError("Failed to load the environment variable 'PGURL'")

    async def get_connection(self) -> AsyncConnection:
        return await AsyncConnection.connect(self.CONNINFO)

    # setup

    @use_cursor(commit=True)
    async def setup(self, cursor):
        await cursor.execute(
            """
            CREATE OR REPLACE FUNCTION update_user_cmds()
                RETURNS TRIGGER
                LANGUAGE plpgsql
            AS $$
            
            DECLARE
                v_channel record;
                v_cmd record;
            
            BEGIN
            
            FOR v_channel IN (SELECT id FROM main_userchannel) LOOP
                FOR v_cmd IN (SELECT id FROM main_command) LOOP
                    INSERT INTO main_channelcommand (channel_id, command_id, is_enabled)
                    VALUES (v_channel.id, v_cmd.id, true)
                    ON CONFLICT (channel_id, command_id) DO NOTHING;
                END LOOP;
            END LOOP;
            
            RETURN NEW;
            
            END;
            $$
            """
        )

        await cursor.execute(
            """
            CREATE OR REPLACE TRIGGER trigger_update_after_channel
            AFTER INSERT ON main_userchannel
            EXECUTE FUNCTION update_user_cmds()
            """
        )

        await cursor.execute(
            """
            CREATE OR REPLACE TRIGGER trigger_update_after_command
            AFTER INSERT ON main_command
            EXECUTE FUNCTION update_user_cmds()
            """
        )

    # AFK

    @use_cursor()
    async def get_afks(self, cursor) -> list[UserAfk]:
        slices, fields = select_fields(UserAfk, User)
        await cursor.execute(
            f"""
            SELECT {fields} FROM main_userafk
            INNER JOIN main_user ON (main_user.id = main_userafk.user_id)
            """
        )
        rows = await cursor.fetchall()
        return [UserAfk(*row[slices[0]], User(*row[slices[1]])) for row in rows]  # type: ignore

    @use_cursor(commit=True)
    async def set_afk(self, user_id: int, username: str, msg: str, cursor) -> UserAfk:
        await self._ensure_user(cursor, user_id, username)

        now = int(time() // 1)
        await cursor.execute(
            f"""
            INSERT INTO main_userafk (msg, timestamp, user_id) VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET msg = %s, timestamp = %s RETURNING id
            """,
            (msg, now, user_id, msg, now)
        )
        afk_id = await cursor.fetchone()

        return UserAfk(afk_id[0], msg, now, User(user_id, username, 0, None, None))

    @use_cursor(commit=True)
    async def remove_afk(self, afk_id: int, cursor) -> None:
        await cursor.execute("DELETE FROM main_userafk WHERE id = %s", (afk_id,))

    # pity

    @use_cursor(commit=True)
    async def get_pity(self, user_id: int, username: str, cursor) -> tuple[int, int]:
        await self._ensure_user(cursor, user_id, username)
        await cursor.execute(
            """
            SELECT four, five FROM main_userpity WHERE user_id = %s;
            """,
            (user_id,)
        )
        pity = await cursor.fetchone()

        if pity is None:
            await cursor.execute(
                """
                INSERT INTO main_userpity (four, five, user_id) VALUES (0, 0, %s)
                """,
                (user_id,)
            )
            return 0, 0

        return pity

    @use_cursor(commit=True)
    async def set_pity(self, user_id: int, four: int, five: int, cursor) -> None:
        await cursor.execute(
            """
            UPDATE main_userpity SET four = %s, five = %s WHERE user_id = %s
            """,
            (four, five, user_id)
        )

    # user

    async def _update_user(
        self,
        cursor,
        user_id: int,
        username: str,
        column: str,
        value,
        default_value=None,
        literal_value=False
    ):
        """Does not commit. Should be done by the calling function."""

        default_value = default_value if default_value is not None else value

        columns = ["id", "username", "money", "can_receive_money", "auto_remove_afk"]
        values = ["%s", "%s", "0", "true", "false"]
        try:
            values[columns.index(column)] = "%s"
        except ValueError:
            columns.append(column)
            values.append("%s")

        if literal_value:
            return await cursor.execute(
                f"""
                INSERT INTO main_user ({','.join(columns)}) VALUES ({','.join(values)})
                ON CONFLICT (id) DO UPDATE SET username = %s, {column} = {value}
                """,
                (user_id, username, default_value, username)
            )

        await cursor.execute(
            f"""
            INSERT INTO main_user ({','.join(columns)}) VALUES ({','.join(values)})
            ON CONFLICT (id) DO UPDATE SET username = %s, {column} = %s;
            """,
            (user_id, username, default_value, username, value)
        )

    async def _ensure_user(self, cursor, user_id: int, username: str):
        """Does not commit. Should be done by the calling function."""

        await cursor.execute(
            """
            INSERT INTO main_user (
                id, username, money, can_receive_money, auto_remove_afk
            ) VALUES (%s, %s, 0, true, false)
            ON CONFLICT (id) DO NOTHING;
            """,
            (user_id, username)
        )

    @use_cursor(commit=True)
    async def update_user_setting(self, user_id: int, username: str, setting: str, value, cursor) -> None:
        if setting not in USER_SETTINGS:
            raise ValueError(f"Invalid setting '{setting}'")

        await self._update_user(cursor, user_id, username, setting, value)

    @use_cursor(commit=True)
    async def get_user(self, user_id: int, username: str, cursor) -> User:
        await self._ensure_user(cursor, user_id, username)
        await cursor.execute(
            f"""
            SELECT {select_fields(User)[1]} FROM main_user WHERE id = %s;
            """,
            (user_id,)
        )
        user = await cursor.fetchone()
        return User(*user)

    @use_cursor()
    async def get_user_if_exists(self, username: str, cursor) -> User | None:
        await cursor.execute(f"SELECT {select_fields(User)[1]} FROM main_user WHERE username = %s", (username,))
        user = await cursor.fetchone()
        return None if user is None else User(*user)

    @use_cursor(commit=True)
    async def add_money(self, user_id: int, username: str, amount: int, cursor) -> None:
        await self._update_user(cursor, user_id, username, "money", f"main_user.money + {amount}", amount, True)

    @use_cursor()
    async def get_top_users(self, cursor):
        await cursor.execute(f"SELECT {select_fields(User)[1]} FROM main_user ORDER BY money DESC LIMIT 5")
        users = await cursor.fetchall()
        return [User(*user) for user in users]

    @use_cursor(commit=True)
    async def get_user_ranking(self, user_id: int, username: str, cursor):
        await self._ensure_user(cursor, user_id, username)
        await cursor.execute(
            f"""
            SELECT rank FROM (
                SELECT RANK() OVER (ORDER BY money DESC) rank, id FROM main_user
            ) ranks where id = %s;
            """,
            (user_id,)
        )
        rank = await cursor.fetchone()
        return rank

    # ac games

    @use_cursor(commit=True)
    async def start_ac_game(self, user_id: int, username: str, cursor) -> AnimeCompareGame:
        await self._ensure_user(cursor, user_id, username)
        await cursor.execute(
            f"""
            INSERT INTO main_animecomparegame (user_id, score, is_finished) VALUES (%s, 0, false) RETURNING id
            """,
            (user_id,)
        )

        return AnimeCompareGame((await cursor.fetchone())[0], 0, False, User(user_id, username, None, None, None))

    async def _get_ac_games_where(self, where: str, cursor, params=None) -> list[AnimeCompareGame] | None:
        slices, fields = select_fields(AnimeCompareGame, User)

        await cursor.execute(
            f"""
            SELECT {fields} FROM main_animecomparegame
            INNER JOIN main_user ON (main_user.id = main_animecomparegame.user_id)
            {where}
            """,
            params
        )
        games = await cursor.fetchall()

        if games is None:
            return

        return [
            AnimeCompareGame(*game[slices[0]], User(*game[slices[1]]))  # type: ignore
            for game in games
        ]

    @use_cursor()
    async def get_in_progress_ac_games(self, cursor) -> list[AnimeCompareGame] | None:
        return await self._get_ac_games_where("WHERE is_finished = false", cursor)

    @use_cursor()
    async def get_top_ac_games(self, cursor) -> list[AnimeCompareGame] | None:
        return await self._get_ac_games_where("WHERE is_finished = true ORDER BY score DESC LIMIT 5", cursor)

    @use_cursor()
    async def get_top_ac_games_for_user(self, user_id: int, cursor) -> list[AnimeCompareGame] | None:
        return await self._get_ac_games_where(
            "WHERE is_finished = true AND user_id = %s ORDER BY score DESC LIMIT 5",
            cursor,
            (user_id,)
        )

    @use_cursor(commit=True)
    async def update_ac_game(self, game_id: int, score: int, cursor) -> None:
        await cursor.execute("UPDATE main_animecomparegame SET score = %s WHERE id = %s", (score, game_id))

    @use_cursor(commit=True)
    async def finish_ac_game(self, game_id: int, cursor) -> None:
        await cursor.execute("UPDATE main_animecomparegame SET is_finished = true WHERE id = %s", (game_id,))

    @use_cursor()
    async def get_user_ac_avg(self, user_id: int, cursor) -> None | float:
        await cursor.execute("SELECT AVG(score) FROM main_animecomparegame WHERE user_id = %s", (user_id,))
        avg = await cursor.fetchone()
        return avg[0] if avg is not None else None

    # osu

    @use_cursor(commit=True)
    async def set_osu_info(
        self,
        user_id: int,
        username: str,
        osu_id: int,
        osu_username: str,
        global_rank: int | None,
        cursor
    ) -> None:
        global_rank = global_rank or 0

        await self._ensure_user(cursor, user_id, username)
        await cursor.execute(
            f"""
            WITH osu AS (
                INSERT INTO main_userosudata (
                    id, username, global_rank
                ) VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET username = %s, global_rank = %s
                RETURNING id
            )
            INSERT INTO main_userosuconnection (user_id, osu_id, is_verified) VALUES (%s, (SELECT id FROM osu), false)
            ON CONFLICT (user_id) DO UPDATE SET osu_id = (SELECT id FROM osu)
            """,
            (osu_id, osu_username, global_rank, osu_username, global_rank, user_id)
        )

    async def _get_osu_from(self, where: str, cursor, params=None) -> UserOsuConnection | None:
        slices, fields = select_fields(UserOsuConnection, UserOsuData, User)

        await cursor.execute(
            f"""
            SELECT {fields} FROM main_userosuconnection
            INNER JOIN main_user ON (main_userosuconnection.user_id = main_user.id)
            INNER JOIN main_userosudata ON (main_userosudata.id = main_userosuconnection.osu_id)
            {where}
            """,
            params
        )
        osu = await cursor.fetchone()

        return None if osu is None else UserOsuConnection(
            *osu[slices[0]],
            UserOsuData(*osu[slices[1]]),  # type: ignore
            User(*osu[slices[2]])  # type: ignore
        )

    @use_cursor()
    async def get_osu_from_username(self, username: str, cursor) -> UserOsuConnection | None:
        return await self._get_osu_from("WHERE main_user.username = %s", cursor, (username,))

    @use_cursor()
    async def get_osu_from_id(self, user_id: int, cursor) -> UserOsuConnection | None:
        return await self._get_osu_from("WHERE main_user.id = %s", cursor, (user_id,))

    # channels

    @use_cursor()
    async def get_channels(self, cursor) -> list[UserChannel]:
        ch_slices, ch_fields = select_fields(UserChannel, User)
        _, cmd_fields = select_fields(Command)
        _, ch_cmd_fields = select_fields(ChannelCommand)

        await cursor.execute(f"SELECT {cmd_fields} FROM main_command ORDER BY id")
        cmds = await cursor.fetchall()
        cmds = [
            Command(*cmd)
            for cmd in cmds
        ]

        await cursor.execute(f"SELECT {ch_cmd_fields} FROM main_channelcommand ORDER BY channel_id, command_id")
        ch_cmds = await cursor.fetchall()
        ch_cmds = [
            ChannelCommand(*ch_cmd, cmd)
            for ch_cmd, cmd in matching_zip(ch_cmds, cmds, lambda ch_cmd, cmd: ch_cmd[2] - cmd.id)
        ]

        def zip_with_cmds(channels):
            ch_iter = iter(channels)
            ch = next(ch_iter)
            lower = 0
            for i, cmd in enumerate(ch_cmds):
                if cmd.channel_id != ch[0]:
                    yield ch, ch_cmds[lower:i]
                    ch = next(ch_iter)
                    lower = i

        await cursor.execute(
            f"""
            SELECT {ch_fields} FROM main_userchannel
            INNER JOIN main_user ON (main_userchannel.user_id = main_user.id)
            ORDER BY main_userchannel.id
            """
        )
        channels = await cursor.fetchall()
        channels = [
            UserChannel(*channel[ch_slices[0]], User(*channel[ch_slices[1]]), cmds)  # type: ignore
            for channel, cmds in zip_with_cmds(channels)
        ]

        return channels

    @use_cursor()
    async def get_channel(self, user_id: int, cursor) -> UserChannel:
        slices, fields = select_fields(UserChannel, User)
        await cursor.execute(
            f"""
            SELECT {fields} FROM main_userchannel
            INNER JOIN main_user ON (main_userchannel.user_id = main_user.id)
            WHERE main_userchannel.user_id = %s
            """,
            (user_id,)
        )
        channel = await cursor.fetchone()
        if channel is None:
            raise ValueError("Invalid user id for getting channel")

        return UserChannel(*channel[slices[0]], User(*channel[slices[1]]), None)

    @use_cursor(commit=True)
    async def sync_commands(self, cmds: list[CallableCommand], cursor):
        await cursor.execute(f"SELECT {select_fields(Command)[1]} FROM main_command")
        old_cmds = [Command(*command) for command in await cursor.fetchall()]

        for cmd in cmds:
            old_cmd = next((old_cmd for old_cmd in old_cmds if old_cmd.name == cmd.name), None)
            if old_cmd is None:
                await self._add_command(cmd, cursor)
            else:
                await self._update_command(old_cmd.id, cmd, cursor)

        for old_cmd in old_cmds:
            cmd = next((cmd for cmd in cmds if cmd.name == old_cmd.name), None)
            if cmd is None:
                await self._remove_command(old_cmd.id, cursor)

    async def _add_command(self, cmd: CallableCommand, cursor):
        await cursor.execute(
            """
            INSERT INTO main_command (name, description, aliases, args) VALUES (%s, %s, %s, %s)
            """,
            (cmd.name, cmd.description, json.dumps(cmd.aliases), json.dumps([arg.json() for arg in cmd.args]))
        )

    async def _update_command(self, cmd_id: int, cmd: CallableCommand, cursor):
        await cursor.execute(
            """
            UPDATE main_command SET description = %s, aliases = %s, args = %s WHERE id = %s
            """,
            (cmd.description, json.dumps(cmd.aliases), json.dumps([arg.json() for arg in cmd.args]), cmd_id)
        )

    async def _remove_command(self, cmd_id: int, cursor):
        await cursor.execute("DELETE FROM main_channelcommand WHERE command_id = %s", (cmd_id,))
        await cursor.execute("DELETE FROM main_command WHERE id = %s", (cmd_id,))

    # timezones

    @use_cursor(commit=True)
    async def set_timezone(self, user_id: int, username: str, timezone: str, cursor) -> None:
        await self._ensure_user(cursor, user_id, username)
        await cursor.execute(
            f"""
            INSERT INTO main_usertimezone (timezone, user_id) VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET timezone = %s;
            """,
            (timezone, user_id, timezone)
        )

    @use_cursor()
    async def get_user_timezone(self, user_id: int, cursor) -> UserTimezone | None:
        slices, fields = select_fields(UserTimezone, User)
        await cursor.execute(
            f"""
            SELECT {fields} FROM main_usertimezone
            INNER JOIN main_user ON (main_user.id = main_usertimezone.user_id)
            WHERE main_user.id = %s
            """,
            (user_id,)
        )
        timezone = await cursor.fetchone()

        return None if timezone is None else UserTimezone(
            *timezone[slices[0]], User(*timezone[slices[1]])  # type: ignore
        )

    # reminders

    @use_cursor()
    async def get_reminders(self, cursor) -> list[UserReminder]:
        slices, fields = select_fields(UserReminder, User, UserChannel)
        # TODO: query is a bit inefficient data bandwidth wise
        await cursor.execute(
            f"""
            SELECT {fields},channel_user.id,channel_user.username FROM main_userreminder
            INNER JOIN main_user ON (main_user.id = main_userreminder.user_id)
            INNER JOIN main_userchannel ON (main_userchannel.id = main_userreminder.channel_id)
            INNER JOIN main_user AS channel_user ON (main_userchannel.user_id = channel_user.id)
            """
        )
        reminders = await cursor.fetchall()
        return [
            UserReminder(
                *reminder[slices[0]],
                User(*reminder[slices[1]]),  # type: ignore
                UserChannel(*reminder[slices[2]], User(*reminder[-2:], None, None, None), None)  # type: ignore
            )
            for reminder in reminders
        ]

    @use_cursor(commit=True)
    async def create_reminder(
        self,
        user_id: int,
        username: str,
        remind_at: int,
        msg: str,
        channel_user_id: int,
        cursor
    ) -> UserReminder:
        await self._ensure_user(cursor, user_id, username)
        await cursor.execute(
            f"""
            WITH channel AS (
                SELECT id FROM main_userchannel WHERE user_id = %s
            )
            INSERT INTO main_userreminder (remind_at, message, user_id, channel_id)
            VALUES (%s, %s, %s, (SELECT id FROM channel)) RETURNING id
            """,
            (channel_user_id, remind_at, msg, user_id)
        )

        return UserReminder(
            (await cursor.fetchone())[0],
            remind_at,
            msg,
            User(user_id, username, None, None, None),
            UserChannel(None, None, User(channel_user_id, None, None, None, None), None)
        )

    @use_cursor(commit=True)
    async def finish_reminder(self, reminder_id: int, cursor):
        await cursor.execute("DELETE FROM main_userreminder WHERE id = %s", (reminder_id,))

    # lastfm

    @use_cursor(commit=True)
    async def set_lastfm(self, user_id: int, username: str, lastfm_username: str, cursor):
        await self._ensure_user(cursor, user_id, username)
        await cursor.execute(
            f"""
            INSERT INTO main_userlastfm (username, user_id) VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET username = %s;
            """,
            (username, user_id, username)
        )

    @use_cursor()
    async def get_lastfm(self, user_id: int, cursor) -> UserLastFM | None:
        slices, fields = select_fields(UserLastFM, User)
        await cursor.execute(
            f"""
            SELECT {fields} FROM main_userlastfm
            INNER JOIN main_user ON (main_user.id = main_userlastfm.user_id)
            WHERE main_userlastfm.user_id = %s
            """,
            (user_id,)
        )
        lastfm = await cursor.fetchone()

        return None if lastfm is None else UserLastFM(*lastfm[slices[0]], User(*lastfm[slices[1]]))  # type: ignore
