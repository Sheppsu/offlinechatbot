from mysql import connector
from datetime import datetime
import os
import json


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
        except connector.Error as err:
            self.database = self.create_connection()

    def close(self):
        self.database.close()

    @property
    def cursor(self):
        self.ping()
        return self.database.cursor()

    def does_user_entry_exist(self, table, user):
        cursor = self.cursor
        cursor.execute(f"SELECT * FROM {table} WHERE username = '{user}'")
        return not not cursor.fetchall()

    def get_afk(self):
        cursor = self.cursor
        cursor.execute("SELECT * FROM afk")
        return {afk[2]: {"message": afk[0], "time": afk[1]} for afk in cursor.fetchall()}

    def save_afk(self, user, message, time=None):
        if time is None:
            time = self.current_time
        if not self.does_user_entry_exist("afk", user):
            self.cursor.execute(f"INSERT INTO afk (message, time, username) VALUES ('{message}', '{time}', '{user}')")
        else:
            self.cursor.execute(f"UPDATE afk SET message = '{message}', time = '{time}' WHERE username = '{user}'")
        self.database.commit()

    def delete_afk(self, user):
        self.cursor.execute(f"DELETE FROM afk WHERE username = '{user}'")
        self.database.commit()

    def get_pity(self):
        cursor = self.cursor
        cursor.execute("SELECT * FROM pity")
        return {pity[0]: {4: pity[1], 5: pity[2]} for pity in cursor.fetchall()}

    def save_pity(self, user, four, five):
        self.cursor.execute(f"UPDATE pity SET four = {four}, five = {five} WHERE username = '{user}'")
        self.database.commit()

    def new_pity(self, user, four=0, five=5):
        self.cursor.execute(f"INSERT INTO pity (username, four, five) VALUES ('{user}', {four}, {five})")
        self.database.commit()

    def get_userdata(self):
        cursor = self.cursor
        cursor.execute("SELECT * FROM userdata")
        return {data[0]: {"money": data[1], "settings": {"receive": bool(data[2])}} for data in cursor.fetchall()}

    def update_userdata(self, user, column, value):
        self.cursor.execute("UPDATE userdata SET %s = %s WHERE username = '%s'" % (column, "'%s'" % value if type(value) == str else value, user))
        self.database.commit()

    def new_user(self, user, money=0, receive=True):
        self.cursor.execute(f"INSERT INTO userdata (username, money, receive) VALUES ('{user}', {money}, {receive})")
        self.database.commit()

    def delete_user(self, user):
        self.cursor.execute(f"DELETE FROM userdata WHERE username = '{user}'")

    def new_animecompare_game(self, user, answer):
        cursor = self.cursor
        cursor.execute(f"INSERT INTO animecompare_games (user, answer) VALUES ('{user}', '{self.format_animecompare_answer(answer)}')")
        self.database.commit()
        cursor.execute("SELECT LAST_INSERT_ID()")
        return cursor.fetchone()[0]

    def get_in_progress_animecompare_games(self):
        cursor = self.cursor
        cursor.execute("SELECT * FROM animecompare_games WHERE finished = 0")
        return [{"id": data[0], "user": data[1], "score": data[2], "answer": json.loads(data[4])} for data in cursor.fetchall()]

    def update_animecompare_game(self, game_id, score, answer):
        self.cursor.execute(f"UPDATE animecompare_games SET score = {score}, answer = '{self.format_animecompare_answer(answer)}' WHERE id = '{game_id}'")
        self.database.commit()

    def finish_animecompare_game(self, game_id):
        self.cursor.execute(f"UPDATE animecompare_games SET finished = 1 WHERE id = {game_id}")
        self.database.commit()

    @staticmethod
    def format_animecompare_answer(answer):
        return json.dumps(answer).replace("'", "\\'")

    @property
    def current_time(self):
        return datetime.now().isoformat()
