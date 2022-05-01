from mysql import connector
from datetime import datetime
import os


class Database:
    def __init__(self):
        self.name = os.getenv("MYSQLDATABASE")
        self.database = connector.connect(
            host=os.getenv("MYSQLHOST"),
            port=int(os.getenv("MYSQLPORT")),
            user=os.getenv("MYSQLUSER"),
            password=os.getenv("MYSQLPASSWORD"),
            database=self.name
        )
        self.cursor = self.database.cursor()

    def does_user_entry_exist(self, table, user):
        self.cursor.execute(f"SELECT * FROM {table} WHERE username = '{user}'")
        return not not self.cursor.fetchall()

    def get_afk(self):
        self.cursor.execute("SELECT * FROM afk")
        return {afk[2]: {"message": afk[0], "time": afk[1]} for afk in self.cursor.fetchall()}

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
        self.cursor.execute("SELECT * FROM pity")
        return {pity[0]: {4: pity[1], 5: pity[2]} for pity in self.cursor.fetchall()}

    def save_pity(self, user, four, five):
        self.cursor.execute(f"UPDATE pity SET four = {four}, five = {five} WHERE username = '{user}'")
        self.database.commit()

    def new_pity(self, user, four=0, five=5):
        self.cursor.execute(f"INSERT INTO pity (username, four, five) VALUES ('{user}', {four}, {five})")
        self.database.commit()

    def get_userdata(self):
        self.cursor.execute("SELECT * FROM userdata")
        return {data[0]: {"money": data[1], "settings": {"receive": bool(data[2])}} for data in self.cursor.fetchall()}

    def update_userdata(self, user, column, value):
        self.cursor.execute(f"UPDATE userdata SET %s = %s" % (column, "'%s'" % value if type(value) == str else value))
        self.database.commit()

    def new_user(self, user, money=0, receive=False):
        self.cursor.execute(f"INSERT INTO userdata (username, money, receive) VALUES ('{user}', {money}, {receive})")
        self.database.commit()

    @property
    def current_time(self):
        return datetime.now().isoformat()


db = Database()
