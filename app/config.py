import os

NODE_ID = int(os.getenv("NODE_ID", "1"))
PORT = int(os.getenv("PORT", "8000"))
SOCKET_PORT = int(os.getenv("SOCKET_PORT", str(9000 + NODE_ID)))
HOST = os.getenv(
    "HOST",
    "http://192.168.56.103:8000"
)


MESSAGE_DELAY = 0