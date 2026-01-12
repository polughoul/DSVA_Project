import os


def _as_int(value: str | None, fallback: int | None) -> int | None:
    try:
        return int(value) if value is not None else fallback
    except (TypeError, ValueError):
        return fallback


def _as_float(value: str | None, fallback: float) -> float:
    try:
        return float(value) if value is not None else fallback
    except (TypeError, ValueError):
        return fallback

NODE_ID = _as_int(os.getenv("NODE_ID"), 1) or 1

PORT = _as_int(os.getenv("PORT"), 8000) or 8000

HOST = os.getenv("HOST", f"http://127.0.0.1:{PORT}")

SOCKET_PORT = _as_int(
    os.getenv("SOCKET_PORT"),
    9000 + NODE_ID
) or (9000 + NODE_ID)


def _resolve_aggregator():
    host = os.getenv("LOG_AGGREGATOR_HOST")
    port = _as_int(os.getenv("LOG_AGGREGATOR_PORT"), None)

    if host and port is None:
        # Pokud je zadán pouze host bez portu, použijeme výchozí 9020
        port = 9020

    if host and port is None:
        # Neplatná konfigurace: agregátor ignorujeme
        host = None

    return host, port


LOG_AGGREGATOR_HOST, LOG_AGGREGATOR_PORT = _resolve_aggregator()

MESSAGE_DELAY = _as_float(os.getenv("MESSAGE_DELAY"), 0.0)

try:  # Optional per-machine overrides without tracking them in Git
    from app.config_local import *  # type: ignore # noqa
except ImportError:
    pass