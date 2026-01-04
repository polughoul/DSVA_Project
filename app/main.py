from fastapi import FastAPI
from app.state import NodeState
from app.api import router
from app.logger import setup_logger
from app.config import NODE_ID, HOST
import app.state as global_state

app = FastAPI()

global_state.state = NodeState(NODE_ID, HOST)

logger = setup_logger(NODE_ID)
logger.info("Node starting...")

app.include_router(router)