import os

from app.node_registry import DEFAULT_LOG_AGGREGATOR, NODE_REGISTRY


def _resolve_int(value, fallback):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


NODE_ID = _resolve_int(os.getenv("NODE_ID", "1"), 1)
_NODE_CONFIG = NODE_REGISTRY.get(NODE_ID, {})

PORT = _resolve_int(
    os.getenv("PORT", str(_NODE_CONFIG.get("port", 8000))),
    8000
)

HOST = os.getenv(
    "HOST",
    _NODE_CONFIG.get("host", f"http://127.0.0.1:{PORT}")
)

SOCKET_PORT = _resolve_int(
    os.getenv(
        "SOCKET_PORT",
        str(_NODE_CONFIG.get("socket_port", 9000 + NODE_ID))
    ),
    9000 + NODE_ID
)


def _resolve_aggregator():
    agg_host = os.getenv("LOG_AGGREGATOR_HOST")
    agg_port_raw = os.getenv("LOG_AGGREGATOR_PORT")

    if not agg_host:
        agg_host = _NODE_CONFIG.get(
            "log_aggregator_host",
            DEFAULT_LOG_AGGREGATOR.get("host")
        )

    if agg_port_raw:
        agg_port = _resolve_int(agg_port_raw, None)
    else:
        agg_port = _NODE_CONFIG.get(
            "log_aggregator_port",
            DEFAULT_LOG_AGGREGATOR.get("port")
        )
        agg_port = _resolve_int(agg_port, None)

    if agg_host and agg_port is None:
        agg_host = None

    return agg_host, agg_port


LOG_AGGREGATOR_HOST, LOG_AGGREGATOR_PORT = _resolve_aggregator()

MESSAGE_DELAY = 0

try:  # Allow optional per-machine overrides without tracking them in Git
    from app.config_local import *  # type: ignore # noqa
except ImportError:
    pass