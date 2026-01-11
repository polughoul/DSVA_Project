"""Shared metadata for known nodes in the ring.

Update NODE_REGISTRY to describe the nodes participating in
the deployment. Each entry can be overridden through environment
variables if needed.
"""

NODE_REGISTRY: dict[int, dict[str, object]] = {
    1: {
        "host": "http://192.168.56.103:8000",
        "port": 8000,
        "socket_port": 9001,
        "log_aggregator_host": "192.168.56.103",
        "log_aggregator_port": 9020,
    },
    2: {
        "host": "http://192.168.56.104:8000",
        "port": 8000,
        "socket_port": 9002,
    },
    3: {
        "host": "http://192.168.56.105:8000",
        "port": 8000,
        "socket_port": 9003,
    },
    4: {
        "host": "http://192.168.56.106:8000",
        "port": 8000,
        "socket_port": 9004,
    },
    5: {
        "host": "http://192.168.56.107:8000",
        "port": 8000,
        "socket_port": 9005,
    },
}

DEFAULT_LOG_AGGREGATOR: dict[str, object] = {
    "host": "192.168.56.103",
    "port": 9020,
}
