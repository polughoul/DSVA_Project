import logging

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
    logger.propagate = False

    return logger