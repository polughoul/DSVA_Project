"""Static registry of known nodes.

Update NODE_REGISTRY to reflect the deployment. Each entry is a
mapping from node id to its base HTTP host and election socket port.
Used for repairing the ring when a neighbour fails.
"""

NODE_REGISTRY: dict[int, dict[str, object]] = {
    1: {
        "host": "http://192.168.56.103:8000",
        "socket_port": 9001,
    },
    2: {
        "host": "http://192.168.56.104:8000",
        "socket_port": 9002,
    },
    3: {
        "host": "http://192.168.56.105:8000",
        "socket_port": 9003,
    },
    4: {
        "host": "http://192.168.56.106:8000",
        "socket_port": 9004,
    },
    5: {
        "host": "http://192.168.56.107:8000",
        "socket_port": 9005,
    },
}
