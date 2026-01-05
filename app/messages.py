import json
from enum import Enum


class MessageType(str, Enum):
    ELECTION = "ELECTION"
    LEADER = "LEADER"
    VAR_GET = "VAR_GET"
    VAR_SET = "VAR_SET"
    VAR_RESPONSE = "VAR_RESPONSE"


def make_message(msg_type: MessageType, from_id: int, data: dict | None = None) -> str:
    return json.dumps({
        "type": msg_type,
        "from": from_id,
        "data": data or {}
    })


def parse_message(raw: str) -> dict:
    return json.loads(raw)
