class AuthorizationHandler:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret

    @property
    def auth_header(self):
        return {
            "X-MAL-CLIENT-ID": self.client_id
        }
