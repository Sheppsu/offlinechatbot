import osu
import os
import json


class Client(osu.Client):
    client_secret = "fda6YO71ZlXxDaCARECjCBl4qusOi5DtjV5Wgb7f"
    client_id = 6833
    redirect_uri = "http://127.0.0.1:8080"

    user = 14895608

    def __init__(self):
        auth = osu.AuthHandler(self.client_id, self.client_secret, self.redirect_uri)
        super().__init__(auth)

    def run(self):
        all_rankings = []
        cursor = None
        for _ in range(4):
            rankings = self.get_ranking("osu", "performance", cursor=cursor)
            cursor = rankings.cursor
            all_rankings += rankings.ranking

        output = [ranking.user.username for ranking in all_rankings]
        with open(f"top players ({len(output)}).json", "w") as f:
            json.dump(output, f)


client = Client()
client.run()
