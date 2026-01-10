import logging
import os
from logging.handlers import SocketHandler

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
    aggregator_host = os.getenv("LOG_AGGREGATOR_HOST")
    aggregator_port = os.getenv("LOG_AGGREGATOR_PORT")

    if aggregator_host and aggregator_port:
        try:
            socket_handler = SocketHandler(
                aggregator_host,
                int(aggregator_port)
            )
            logger.addHandler(socket_handler)
        except (ValueError, OSError):
            logger.warning(
                "Failed to attach aggregator handler (%s:%s)",
                aggregator_host,
                aggregator_port
            )
    logger.propagate = False

    return logger