import os

NODE_ID = int(os.getenv("NODE_ID", "1"))
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv(
    "HOST",
    "http://192.168.56.103:8000"
)


MESSAGE_DELAY = 0