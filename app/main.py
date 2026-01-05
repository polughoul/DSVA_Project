from fastapi import FastAPI
import threading
import app.state as global_state
from app.state import NodeState
from app.api import router
from app.config import NODE_ID, HOST, SOCKET_PORT
from app.socket_server import start_socket_server
from app.logger import setup_logger

app = FastAPI()

global_state.state = NodeState(NODE_ID, HOST, SOCKET_PORT)

logger = setup_logger(NODE_ID)
logger.info("Node starting...")

threading.Thread(
    target=start_socket_server,
    args=("0.0.0.0", SOCKET_PORT),
    daemon=True
).start()

app.include_router(router)