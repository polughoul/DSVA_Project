from fastapi import APIRouter, Body, HTTPException
import app.state as global_state
from app.logger import setup_logger
from app.state import NodeInfo
import requests
import time
from app.config import NODE_ID
from app.socket_client import send_socket_message

router = APIRouter()
logger = setup_logger(NODE_ID)


# =========================
# Delay-aware send
# =========================
def send_with_delay(url, json=None, timeout=2):
    state = getattr(global_state, "state", None)
    if state and state.delay > 0:
        time.sleep(state.delay)
    return requests.post(url, json=json, timeout=timeout)


@router.post("/update_neighbors")
def update_neighbors(payload: dict = Body(...)):
    state = global_state.state

    if "prev_id" in payload:
        prev_id = payload.get("prev_id")
        prev_host = payload.get("prev_host")
        prev_socket_port = payload.get("prev_socket_port")

        if prev_id is None:
            state.prev_node = None
        elif prev_host and prev_socket_port is not None:
            state.prev_node = NodeInfo(prev_id, prev_host, prev_socket_port)

    if "next_id" in payload:
        next_id = payload.get("next_id")
        next_host = payload.get("next_host")
        next_socket_port = payload.get("next_socket_port")

        if next_id is None:
            state.next_node = None
        elif next_host and next_socket_port is not None:
            state.next_node = NodeInfo(next_id, next_host, next_socket_port)

    logger.info(
        "Neighbors updated: prev=%s, next=%s",
        state.prev_node.node_id if state.prev_node else None,
        state.next_node.node_id if state.next_node else None,
    )

    return {"message": "Neighbors updated"}


def get_next_alive_node():
    state = global_state.state
    current = state.next_node
    visited = set()

    while current and current.node_id not in visited:
        visited.add(current.node_id)
        try:
            response = requests.get(f"{current.host}/health", timeout=1)
            data = response.json()

            if data.get("status") == "alive":
                return current

            next_info = data.get("next")
            if not next_info:
                return None

            current = NodeInfo(
                next_info["node_id"],
                next_info["host"],
                next_info.get("socket_port", current.socket_port),
            )
        except requests.exceptions.RequestException:
            return None

    return None


def broadcast_leader(leader_id: int):
    state = global_state.state
    current = state.next_node

    if not current:
        return

    visited = set()
    payload = {
        "leader_id": leader_id,
        "leader_host": state.self_host,
        "leader_socket_port": state.socket_port,
    }

    while current and current.node_id not in visited:
        visited.add(current.node_id)
        try:
            send_with_delay(f"{current.host}/leader", json=payload, timeout=1)
        except requests.exceptions.RequestException:
            logger.warning("Leader broadcast failed")

        try:
            response = requests.get(f"{current.host}/health", timeout=1)
            next_info = response.json().get("next")
            if not next_info:
                break

            current = NodeInfo(
                next_info["node_id"],
                next_info["host"],
                next_info.get("socket_port", state.socket_port),
            )
        except Exception:
            break


# =========================
# Join / Leave
# =========================
@router.post("/join")
def join(node_id: int = Body(...), host: str = Body(...), socket_port: int = Body(...)):
    state = global_state.state
    logger.info(f"Join request from node {node_id}")

    if node_id == state.node_id:
        return {"message": "Cannot join myself"}

    if state.next_node and state.next_node.node_id == node_id:
        return {"message": "Node already in ring"}

    new_node = NodeInfo(node_id, host, socket_port)

    if state.next_node is None:
        state.next_node = new_node
        state.prev_node = new_node

        send_with_delay(
            f"{host}/update_neighbors",
            json={
                "prev_id": state.node_id,
                "prev_host": state.self_host,
                "prev_socket_port": state.socket_port,

                "next_id": state.node_id,
                "next_host": state.self_host,
                "next_socket_port": state.socket_port,
            }
        )

        return {"message": "Joined as second node"}

    old_next = state.next_node
    state.next_node = new_node

    send_with_delay(
        f"{host}/update_neighbors",
        json={
            "prev_id": state.node_id,
            "prev_host": state.self_host,
            "prev_socket_port": state.socket_port,

            "next_id": old_next.node_id,
            "next_host": old_next.host,
            "next_socket_port": old_next.socket_port,
        }
    )

    send_with_delay(
        f"{old_next.host}/update_neighbors",
        json={
            "prev_id": node_id,
            "prev_host": host,
            "prev_socket_port": socket_port,
        }
    )

    return {"message": "Node joined"}


@router.post("/leave")
def leave():
    state = global_state.state
    logger.info("Node leaving ring")

    try:
        if state.prev_node and state.next_node:
            send_with_delay(
                f"{state.prev_node.host}/update_neighbors",
                json={
                    "next_id": state.next_node.node_id,
                    "next_host": state.next_node.host,
                    "next_socket_port": state.next_node.socket_port,
                }
            )

            send_with_delay(
                f"{state.next_node.host}/update_neighbors",
                json={
                    "prev_id": state.prev_node.node_id,
                    "prev_host": state.prev_node.host,
                    "prev_socket_port": state.prev_node.socket_port,
                }
            )

    except Exception as e:
        logger.warning(f"Leave propagation failed: {e}")

    state.next_node = None
    state.prev_node = None
    state.leader_id = None
    state.in_election = False
    state.leader_node = None

    return {"message": "Left ring"}



# =========================
# Health & lifecycle
# =========================
@router.get("/health")
def health():
    state = global_state.state
    return {
        "status": "alive" if state.alive else "killed",
        "node_id": state.node_id,
        "leader_id": state.leader_id,
        "is_leader": state.leader_id == state.node_id,
        "delay": state.delay,
        "next": state.next_node.to_dict() if state.next_node else None,
        "prev": state.prev_node.to_dict() if state.prev_node else None
    }


@router.post("/kill")
def kill():
    state = global_state.state
    state.alive = False
    state.leader_id = None
    state.in_election = False
    state.leader_node = None
    logger.info("Node killed (communication disabled)")
    return {"message": "Node killed", "node_id": state.node_id}


@router.post("/revive")
def revive():
    state = global_state.state
    state.alive = True
    state.leader_id = None
    state.in_election = False
    state.leader_node = None
    logger.info("Node revived (communication restored)")
    return {"message": "Node revived"}


@router.post("/setDelay")
def set_delay(delay: float = Body(..., embed=True)):
    state = global_state.state
    state.delay = delay
    logger.info(f"Delay set to {delay}")
    return {"message": "Delay updated", "delay": delay}


# =========================
# Election (Chang–Roberts)
# =========================
@router.post("/startElection")
def start_election():
    state = global_state.state

    if not state.alive:
        raise HTTPException(status_code=503, detail="Node is killed")

    if state.in_election:
        return {"message": "Election already running"}

    if not state.next_node:
        return {"error": "Node not in ring"}

    if state.next_node.node_id == state.node_id:
        return {"error": "Single-node ring"}

    logger.info("Starting election")
    state.in_election = True
    state.leader_id = None
    state.leader_node = None

    ip, port = state.next_node.socket_addr()

    response = send_socket_message(
        host=ip,
        port=port,
        message={
            "type": "ELECTION",
            "candidate_id": state.node_id
        }
    )

    if isinstance(response, dict) and response.get("error") == "SOCKET_COMM_ERROR":
        state.in_election = False
        raise HTTPException(status_code=503, detail="Failed to reach next node via socket")

    return {"message": "Election started"}



@router.post("/election")
def election(candidate_id: int = Body(..., embed=True)):
    state = global_state.state

    if not state.alive:
        raise HTTPException(status_code=503, detail="Node is killed")

    logger.info(f"Election message received: {candidate_id}")

    if candidate_id > state.node_id:
        forward_id = candidate_id
    elif candidate_id < state.node_id:
        forward_id = state.node_id
    else:
        logger.info("I am the leader")
        state.leader_id = state.node_id
        state.in_election = False
        state.leader_node = state.self_info()
        broadcast_leader(state.node_id)
        return {"message": "Leader elected"}

    next_alive = get_next_alive_node()
    if not next_alive:
        state.in_election = False
        return {"error": "No alive nodes to continue election"}

    try:
        send_with_delay(
            f"{next_alive.host}/election",
            json={"candidate_id": forward_id}
        )
    except requests.exceptions.RequestException:
        logger.warning("Election forwarding failed")

    return {"message": "Election forwarded"}


@router.post("/leader")
def leader(
    leader_id: int = Body(...),
    leader_host: str | None = Body(None),
    leader_socket_port: int | None = Body(None)
):
    state = global_state.state

    if not state.alive:
        return {"message": "Node killed"}

    state.leader_id = leader_id
    if leader_host and leader_socket_port:
        state.leader_node = NodeInfo(leader_id, leader_host, leader_socket_port)
    elif leader_id == state.node_id:
        state.leader_node = state.self_info()
    state.in_election = False
    logger.info(f"Leader set to {leader_id}")
    return {"message": "Leader acknowledged"}


def _trigger_election(reason: str):
    state = global_state.state

    if not state.alive:
        return False, "Local node is killed"

    if not state.next_node:
        return False, "Node not in ring"

    if state.next_node.node_id == state.node_id:
        return False, "Single-node ring"

    if state.in_election:
        logger.info(f"{reason} - election already running")
        return True, None

    logger.warning(f"{reason} - triggering election")

    state.leader_id = None
    state.leader_node = None

    try:
        start_election()
        return True, None
    except HTTPException as exc:
        logger.warning(f"Election trigger failed: {exc.detail}")
        return False, exc.detail


def _raise_with_election(status_code: int, base_detail: str, reason: str):
    success, failure_detail = _trigger_election(reason)
    if success:
        raise HTTPException(status_code=status_code, detail=f"{base_detail} - election restarted")

    failure_msg = failure_detail or "election could not be started"
    raise HTTPException(status_code=status_code, detail=f"{base_detail} - election failed: {failure_msg}")


# =========================
# Shared variable
# =========================
@router.get("/variable")
def get_variable():
    state = global_state.state

    if not state.alive:
        raise HTTPException(status_code=503, detail="Node is killed")

    if state.leader_node is None:
        return {"error": "No leader elected"}

    if state.leader_id == state.node_id:
        return {
            "value": state.shared_value,
            "served_by": state.node_id
        }

    response = send_socket_message(
        *state.leader_node.socket_addr(),
        {"type": "GET_VAR"}
    )

    if response is None:
        _raise_with_election(504, "Leader did not respond", "Leader timeout during GET_VAR")

    if isinstance(response, dict):
        error_code = response.get("error")
        if error_code == "SOCKET_COMM_ERROR":
            _raise_with_election(503, "Leader socket unreachable", "Leader socket unreachable during GET_VAR")

        if error_code in {"NODE_KILLED", "NOT_LEADER"}:
            _raise_with_election(503, "Leader unavailable", f"Leader responded with {error_code} during GET_VAR")

    return response



@router.post("/variable")
def set_variable(value: int = Body(..., embed=True)):
    state = global_state.state

    if not state.alive:
        raise HTTPException(status_code=503, detail="Node is killed")

    if state.leader_node is None:
        return {"error": "No leader elected"}

    if state.leader_id == state.node_id:
        state.shared_value = value
        return {
            "status": "OK",
            "value": value,
            "set_by": state.node_id
        }

    response = send_socket_message(
        *state.leader_node.socket_addr(),
        {
            "type": "SET_VAR",
            "value": value
        }
    )

    if response is None:
        _raise_with_election(504, "Leader did not respond", "Leader timeout during SET_VAR")

    if isinstance(response, dict):
        error_code = response.get("error")
        if error_code == "SOCKET_COMM_ERROR":
            _raise_with_election(503, "Leader socket unreachable", "Leader socket unreachable during SET_VAR")

        if error_code in {"NODE_KILLED", "NOT_LEADER"}:
            _raise_with_election(503, "Leader unavailable", f"Leader responded with {error_code} during SET_VAR")

    return response














