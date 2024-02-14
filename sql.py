from mysql import connector
from datetime import datetime, timezone as tz
from helper_objects import ChannelCommandInclusion, ChannelConfig
from dataclasses import dataclass
import os
import json


@dataclass
class User:
    username: str
    money: int
    receive: bool
    autoafk: bool
    userid: int


@dataclass
class AFK:
    message: str
    time: datetime
    username: str

    @classmethod
    def from_db_data(cls, data):
        return cls(
            data[0],
            datetime.fromisoformat(data[1]),
            data[2]
        )


USER_SETTINGS = (
    "receive", "autoafk"
)


def sqlstr(s):
    return "'"+s.replace("'", "''")+"'"


class Database:
    name = os.getenv("MYSQLDATABASE")
    host = os.getenv("MYSQLHOST")
    port = int(os.getenv("MYSQLPORT"))
    user = os.getenv("MYSQLUSER")
    password = os.getenv("MYSQLPASSWORD")

    def __init__(self):
        self.name = os.getenv("MYSQLDATABASE")
        self.database = self.create_connection()

    def create_connection(self):
        return connector.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.name
        )

    def ping(self):
        try:
            self.database.ping(reconnect=True, attempts=3, delay=5)
        except connector.Error:
            self.database = self.create_connection()

    def close(self):
        self.database.close()

    def get_cursor(self):
        self.ping()
        return self.database.cursor()

    # afk

    def add_afk(self, user, message):
        self.get_cursor().execute(
            f"INSERT INTO afk (message, time, username) VALUES ({sqlstr(message)}, {sqlstr(self.current_time)}, {sqlstr(user)})"
        )
        self.database.commit()

    def save_afk(self, user, message):
        self.get_cursor().execute(
            f"UPDATE afk SET message = {sqlstr(message)}, time = {sqlstr(self.current_time)} WHERE username = {sqlstr(user)}"
        )
        self.database.commit()

    def delete_afk(self, user):
        self.get_cursor().execute(f"DELETE FROM afk WHERE username = '{user}'")
        self.database.commit()

    def get_afks(self):
        cursor = self.get_cursor()
        cursor.execute("SELECT username FROM afk")
        return sum(cursor.fetchall(), ())

    def get_afk(self, username):
        cursor = self.get_cursor()
        cursor.execute(f"SELECT * FROM afk WHERE username = {sqlstr(username)}")
        afk = cursor.fetchone()
        return AFK.from_db_data(afk) if afk else None

    @property
    def current_time(self):
        return datetime.now(tz=tz.utc).isoformat()

    # pity

    def save_pity(self, user, four, five):
        self.get_cursor().execute(f"UPDATE pity SET four = {four}, five = {five} WHERE username = '{user}'")
        self.database.commit()

    def new_pity(self, user, four=0, five=5):
        self.get_cursor().execute(f"INSERT INTO pity (username, four, five) VALUES ('{user}', {four}, {five})")
        self.database.commit()

    def get_user_pity(self, username):
        cursor = self.get_cursor()
        cursor.execute(f"SELECT four, five FROM pity WHERE username = {sqlstr(username)}")
        pity = cursor.fetchone()
        return pity if pity else None

    # user data

    def insert_user_and_do(self, ctx, line):
        cursor = self.get_cursor()
        cursor.execute(f"INSERT IGNORE INTO userdata (username, userid) VALUES ({sqlstr(ctx.sending_user)}, {ctx.user_id})")
        self.database.commit()
        cursor.execute(line)
        return cursor

    def update_userdata(self, ctx, column, value):
        self.insert_user_and_do(ctx, f"UPDATE userdata SET {column} = {sqlstr(value)} WHERE userid = {ctx.user_id}")
        self.database.commit()

    def add_money(self, ctx, amount):
        self.insert_user_and_do(ctx, f"UPDATE userdata SET money = money + {amount} WHERE userid = {ctx.user_id}")
        self.database.commit()

    def get_balance(self, ctx, username=None):
        if username is not None:
            cursor = self.get_cursor()
            cursor.execute(f"SELECT money FROM userdata WHERE username = {sqlstr(username)}")
        else:
            cursor = self.insert_user_and_do(ctx, f"SELECT money FROM userdata WHERE userid = {ctx.user_id}")
        return cursor.fetchone()[0]

    def delete_user(self, user_id):
        self.get_cursor().execute(f"DELETE FROM userdata WHERE userid = {user_id}")
        self.database.commit()

    def get_top_users(self):
        cursor = self.get_cursor()
        cursor.execute("SELECT username, money FROM userdata ORDER BY money DESC LIMIT 5")
        return cursor.fetchall()

    def get_user_ranking(self, ctx):
        cursor = self.get_cursor()
        cursor.execute("SELECT rnk FROM "
                       "(SELECT userid, RANK() OVER (ORDER BY money DESC) AS rnk FROM userdata) AS ranks "
                       f"WHERE ranks.userid = {ctx.user_id} LIMIT 1")
        return cursor.fetchone()[0]

    def get_user_from_username(self, username):
        cursor = self.get_cursor()
        cursor.execute(f"SELECT * FROM userdata WHERE username = {sqlstr(username)}")
        user = cursor.fetchone()
        return User(*user) if user else None

    def get_current_user(self, ctx):
        cursor = self.insert_user_and_do(ctx, f"SELECT * FROM userdata WHERE userid = {ctx.user_id}")
        return User(*cursor.fetchone())

    def get_and_delete_old_user(self, username):
        cursor = self.get_cursor()
        cursor.execute(f"SELECT money FROM old_userdata WHERE username = {sqlstr(username)};"
                       f"DELETE FROM old_userdata WHERE username = {sqlstr(username)}")
        money = cursor.fetchone()
        return money[0] if money else None

    # anime compare

    def new_animecompare_game(self, user):
        cursor = self.get_cursor()
        cursor.execute(f"INSERT INTO animecompare_games (user) VALUES ('{user}')")
        self.database.commit()
        cursor.execute("SELECT LAST_INSERT_ID()")
        return cursor.fetchone()[0]

    def get_in_progress_animecompare_games(self):
        cursor = self.get_cursor()
        cursor.execute("SELECT * FROM animecompare_games WHERE finished = 0")
        return [{"id": data[0], "user": data[1], "score": data[2]} for data in cursor.fetchall()]

    def get_top_animecompare_games(self):
        cursor = self.get_cursor()
        cursor.execute("SELECT * FROM animecompare_games WHERE finished = 1 ORDER BY score DESC LIMIT 5")
        return [{"id": data[0], "user": data[1], "score": data[2]} for data in cursor.fetchall()]

    def get_top_animecompare_game_for_user(self, user):
        cursor = self.get_cursor()
        cursor.execute(f"SELECT * FROM animecompare_games WHERE finished = 1 AND user = {sqlstr(user)} ORDER BY score DESC LIMIT 1")
        return [{"id": data[0], "user": data[1], "score": data[2]} for data in cursor.fetchall()]

    def update_animecompare_game(self, game_id, score):
        self.get_cursor().execute(f"UPDATE animecompare_games SET score = {score} WHERE id = '{game_id}'")
        self.database.commit()

    def finish_animecompare_game(self, game_id):
        self.get_cursor().execute(f"UPDATE animecompare_games SET finished = 1 WHERE id = {game_id}")
        self.database.commit()

    def get_ac_user_average(self, username):
        cursor = self.get_cursor()
        cursor.execute(f"SELECT AVG(score) FROM animecompare_games WHERE user = {sqlstr(username)}")
        avg_score = cursor.fetchone()
        return avg_score[0] if avg_score else None

    # osu

    def new_osu_data(self, user_id, osu_username, osu_user_id):
        self.get_cursor().execute(f"INSERT INTO osu_data (user_id, osu_user_id, osu_username) VALUES ({user_id}, {osu_user_id}, '{osu_username}')")
        self.database.commit()

    def update_osu_data(self, user_id, osu_username, osu_user_id):
        self.get_cursor().execute(f"UPDATE osu_data SET osu_user_id = {osu_user_id}, osu_username = '{osu_username}', verified = 0 WHERE user_id = '{user_id}'")
        self.database.commit()

    def get_osu_user_from_username(self, username):
        cursor = self.get_cursor()
        cursor.execute(f"SELECT osu_user_id, osu_username, verified FROM osu_data INNER JOIN userdata ON (userdata.userid = osu_data.user_id) WHERE userdata.username = {sqlstr(username)}")
        osu_user = cursor.fetchone()
        return osu_user if osu_user else None

    # channels

    def get_channels(self):
        cursor = self.get_cursor()
        cursor.execute("SELECT * FROM channels")
        return [ChannelConfig(data[0], int(data[1]), ChannelCommandInclusion(int(data[2])), bool(data[3]), json.loads(data[4])) for data in cursor.fetchall()]

    def add_channel(self, name, user_id, channel_inclusion, offlineonly, commands):
        self.get_cursor().execute("INSERT INTO channels (name, id, channel_inclusion, offlineonly, commands) "
                            f"VALUES ({sqlstr(name)}, {user_id}, {channel_inclusion}, {offlineonly}, {sqlstr(commands)})")
        self.database.commit()

    # timezones

    def add_timezone(self, userid, timezone_name):
        self.get_cursor().execute(f"INSERT INTO timezones (userid, timezone) VALUES ({userid}, {sqlstr(timezone_name)})")
        self.database.commit()

    def update_timezone(self, userid, timezone_name):
        self.get_cursor().execute(f"UPDATE timezones SET timezone = {sqlstr(timezone_name)} WHERE userid = {userid}")
        self.database.commit()

    def get_user_timezone(self, userid):
        cursor = self.get_cursor()
        cursor.execute(f"SELECT timezone FROM timezones WHERE userid = {userid}")
        timezone = cursor.fetchone()
        return timezone[0] if timezone else None

    # misc

    def save_messages(self, ctx, buffer):
        context = "\n".join(map(lambda ctx: f"{ctx.user.display_name}: {ctx.message}", buffer))
        self.get_cursor().execute("INSERT INTO messages (userid, username, message, context) "
                            f"VALUES ({ctx.user_id}, {sqlstr(ctx.user.display_name)}, {sqlstr(ctx.message)}, {sqlstr(context)})")
        self.database.commit()
