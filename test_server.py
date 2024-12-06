import socket
import json


def send_message(data):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('127.0.0.1', 8727))
    s.send(json.dumps(data).encode('utf-8'))
    s.close()


if __name__ == "__main__":
    send_message({"cmd": 0, "channel_id": 19})
