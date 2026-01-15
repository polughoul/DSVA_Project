import socket
import json
import threading

import requests

import app.state as global_state
from app.logger import setup_logger
from app.node_registry import NODE_REGISTRY
from app.socket_client import send_socket_message
from app.state import NodeInfo

logger = setup_logger("socket-server")


def describe_message(msg: dict) -> str:
    msg_type = msg.get("type", "UNKNOWN")

    if msg_type == "ELECTION":
        candidate = msg.get("candidate_id")
        return f"ELECTION candidate={candidate}"

    if msg_type == "LEADER":
        leader_id = msg.get("leader_id")
        return f"LEADER leader={leader_id}"

    if msg_type == "GET_VAR":
        return "GET_VAR request"

    if msg_type == "SET_VAR":
        value = msg.get("value")
        return f"SET_VAR value={value}"

    if msg_type == "PING":
        return "PING"

    return msg_type


def start_socket_server(host: str, port: int):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen()

    logger.info(
        f"node={global_state.state.node_id if global_state.state else '?'}: server listening on {host}:{port}"
    )

    while True:
        conn, addr = server.accept()
        threading.Thread(
            target=handle_client,
            args=(conn, addr),
            daemon=True
        ).start()


def handle_client(conn: socket.socket, addr):
    state = global_state.state
    try:
        data = conn.recv(4096).decode().strip()
        if not data:
            return

        message = json.loads(data)
        summary = describe_message(message)
        logger.info(
            "node=%s: received %s from %s",
            state.node_id,
            summary,
            addr[0]
        )

        response = handle_message(message)
        if response is not None:
            conn.sendall((json.dumps(response) + "\n").encode())

    except Exception as e:
        logger.warning(
            "node=%s: socket error from host=%s error=%s",
            state.node_id,
            addr[0],
            e
        )

    finally:
        conn.close()


def handle_message(msg: dict):
    msg_type = msg.get("type")

    if msg_type == "PING":
        return {"status": "OK"}

    if msg_type == "ELECTION":
        return handle_election(msg)

    if msg_type == "LEADER":
        return handle_leader(msg)

    if msg_type == "GET_VAR":
        return handle_get_var()

    if msg_type == "SET_VAR":
        return handle_set_var(msg)

    return {"error": "Unknown message type"}


def _registry_node_info(node_id: int) -> NodeInfo | None:
    entry = NODE_REGISTRY.get(node_id)
    if not entry:
        return None

    host = entry.get("host")
    socket_port = entry.get("socket_port")

    if not host:
        return None

    try:
        port_value = int(socket_port) if socket_port is not None else 9000 + node_id
    except (TypeError, ValueError):
        port_value = 9000 + node_id

    return NodeInfo(node_id, host, port_value)


def _iter_successor_candidates(exclude: set[int]) -> list[NodeInfo]:
    state = global_state.state
    ids = sorted(NODE_REGISTRY.keys())

    if state.node_id in ids:
        start_index = ids.index(state.node_id) + 1
        ordered_ids = ids[start_index:] + ids[:start_index]
    else:
        ordered_ids = ids

    candidates: list[NodeInfo] = []
    for candidate_id in ordered_ids:
        if candidate_id in exclude:
            continue

        node_info = _registry_node_info(candidate_id)
        if node_info:
            candidates.append(node_info)

    return candidates


def _probe_alive(host: str, timeout: float = 2.0) -> bool:
    try:
        response = requests.get(f"{host}/health", timeout=timeout)
        data = response.json()
        return data.get("status") == "alive"
    except (requests.RequestException, ValueError):
        return False


def _find_replacement_successor(exclude: set[int]) -> NodeInfo | None:
    for candidate in _iter_successor_candidates(exclude):
        if _probe_alive(candidate.host):
            return candidate
    return None


def _fetch_next_of(node: NodeInfo | None) -> NodeInfo | None:
    if not node:
        return None

    try:
        response = requests.get(f"{node.host}/health", timeout=2)
        data = response.json()
        next_info = data.get("next")
        if not next_info:
            return None

        return NodeInfo(
            next_info["node_id"],
            next_info["host"],
            next_info.get("socket_port", node.socket_port)
        )
    except (requests.RequestException, ValueError, KeyError):
        return None


def _repair_topology(missing_id: int | None) -> bool:
    state = global_state.state

    if not state.next_node:
        return False

    exclude = {state.node_id}
    if missing_id is not None:
        exclude.add(missing_id)

    replacement: NodeInfo | None = None

    if state.next_next_node and state.next_next_node.node_id not in exclude:
        if _probe_alive(state.next_next_node.host):
            replacement = state.next_next_node

    if not replacement:
        replacement = _find_replacement_successor(exclude)

    if not replacement:
        logger.warning(
            "node=%s: topology repair failed - no alive successor found",
            state.node_id
        )
        state.set_next(None)
        state.set_next_next(None)
        return False

    state.set_next(replacement)
    state.set_next_next(_fetch_next_of(replacement) or state.self_info())

    try:
        requests.post(
            f"{replacement.host}/update_neighbors",
            json={
                "prev_id": state.node_id,
                "prev_host": state.self_host,
                "prev_socket_port": state.socket_port,
            },
            timeout=2
        )
    except requests.RequestException as exc:
        logger.warning(
            "node=%s: failed to update new successor prev pointer (%s)",
            state.node_id,
            exc
        )
        return False

    if state.prev_node:
        try:
            requests.post(
                f"{state.prev_node.host}/update_neighbors",
                json={
                    "next_next_id": replacement.node_id,
                    "next_next_host": replacement.host,
                    "next_next_socket_port": replacement.socket_port,
                },
                timeout=2
            )
        except requests.RequestException as exc:
            logger.warning(
                "node=%s: failed to inform predecessor about repaired successor (%s)",
                state.node_id,
                exc
            )

    logger.info(
        "node=%s: topology repaired - new successor %s",
        state.node_id,
        replacement.node_id
    )

    return True


def _forward_election(candidate_id: int, allow_repair: bool = True):
    state = global_state.state

    if not state.next_node:
        logger.warning("node=%s: no next node to forward election message", state.node_id)
        return {"error": "NO_NEXT_NODE"}

    if state.next_node.node_id == state.node_id:
        state.leader_id = state.node_id
        state.leader_node = state.self_info()
        state.in_election = False
        logger.info("node=%s: single-node ring - became leader", state.node_id)
        return {"status": "LEADER"}

    ip, port = state.next_node.socket_addr()

    response = send_socket_message(
        host=ip,
        port=port,
        message={
            "type": "ELECTION",
            "candidate_id": candidate_id
        }
    )

    if isinstance(response, dict) and response.get("error") == "SOCKET_COMM_ERROR":
        failed_id = state.next_node.node_id if state.next_node else None
        logger.warning("node=%s: election forward error", state.node_id)

        if allow_repair and failed_id is not None and _repair_topology(failed_id):
            logger.info("node=%s: restarting election after topology repair", state.node_id)
            return _forward_election(candidate_id, allow_repair=False)

        return {"error": "SOCKET_COMM_ERROR"}

    return {"status": "FORWARDED"}

def handle_election(msg: dict):
    state = global_state.state
    candidate_id = msg["candidate_id"]

    if not state.alive:
        logger.info("node=%s: forwarding election while killed", state.node_id)
        return _forward_election(candidate_id)

    if candidate_id > state.node_id:
        forward_id = candidate_id
    elif candidate_id < state.node_id:
        forward_id = state.node_id
    else:
        state.leader_id = state.node_id
        state.leader_node = state.self_info()
        state.in_election = False

        logger.info("node=%s: elected self as leader", state.node_id)

        if not state.next_node:
            return {"status": "LEADER"}

        ip, port = state.next_node.socket_addr()

        response = send_socket_message(
            ip,
            port,
            {
                "type": "LEADER",
                "leader_id": state.node_id,
                "leader_host": state.self_host,
                "leader_socket_port": state.socket_port
            }
        )

        if isinstance(response, dict) and response.get("error") == "SOCKET_COMM_ERROR":
            logger.warning("node=%s: leader broadcast failed", state.node_id)

        return {"status": "LEADER"}

    return _forward_election(forward_id)

def handle_leader(msg: dict):
    state = global_state.state

    if not state.alive:
        logger.info("node=%s: ignored leader notice (node killed)", state.node_id)

        if state.next_node:
            send_socket_message(
                *state.next_node.socket_addr(),
                msg
            )

        return {"status": "IGNORED"}

    state.leader_id = msg["leader_id"]
    state.leader_node = global_state.NodeInfo(
        msg["leader_id"],
        msg["leader_host"],
        msg["leader_socket_port"]
    )
    state.in_election = False

    logger.info("node=%s: leader accepted leader_id=%s", state.node_id, state.leader_id)

    if state.node_id != state.leader_id and state.next_node:
        send_socket_message(
            *state.next_node.socket_addr(),
            msg
        )

    return {"status": "OK"}




def handle_get_var():
    state = global_state.state

    if not state.alive:
        logger.info("node=%s: GET_VAR rejected - node killed", state.node_id)
        return {"error": "NODE_KILLED"}

    if state.leader_id != state.node_id:
        logger.info(
            "node=%s: GET_VAR redirected - not leader (current_leader=%s)",
            state.node_id,
            state.leader_id
        )
        return {
            "error": "NOT_LEADER",
            "leader_id": state.leader_id
        }

    logger.info(
        "node=%s: GET_VAR served locally value=%s",
        state.node_id,
        state.shared_value
    )
    return {
        "value": state.shared_value,
        "leader_id": state.node_id
    }



def handle_set_var(msg):
    state = global_state.state

    if not state.alive:
        logger.info("node=%s: SET_VAR rejected - node killed", state.node_id)
        return {"error": "NODE_KILLED"}

    if state.leader_id != state.node_id:
        logger.info(
            "node=%s: SET_VAR redirected - not leader (current_leader=%s)",
            state.node_id,
            state.leader_id
        )
        return {
            "error": "NOT_LEADER",
            "leader_id": state.leader_id
        }

    value = msg["value"]
    state.shared_value = value

    logger.info("node=%s: shared variable set to %s", state.node_id, value)

    return {
        "status": "OK",
        "value": value,
        "leader_id": state.node_id
    }




