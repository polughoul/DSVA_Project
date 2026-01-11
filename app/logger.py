import logging
from logging.handlers import SocketHandler

from app.config import LOG_AGGREGATOR_HOST, LOG_AGGREGATOR_PORT

def setup_logger(node_id: int):
    logger = logging.getLogger(f"node-{node_id}")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [Node %(name)s] %(message)s"
    )

    ch = logging.StreamHandler()
    ch.setFormatter(formatter)

   
    fh = logging.FileHandler(f"node_{node_id}.log")
    fh.setFormatter(formatter)

    logger.addHandler(ch)
    logger.addHandler(fh)
    if LOG_AGGREGATOR_HOST and LOG_AGGREGATOR_PORT:
        try:
            socket_handler = SocketHandler(
                LOG_AGGREGATOR_HOST,
                LOG_AGGREGATOR_PORT
            )
            logger.addHandler(socket_handler)
        except (ValueError, OSError):
            logger.warning(
                "Failed to attach aggregator handler (%s:%s)",
                LOG_AGGREGATOR_HOST,
                LOG_AGGREGATOR_PORT
            )
    logger.propagate = False

    return logger