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


_UNSET = object()


def send_with_delay(url, json=None, timeout=2):
    state = getattr(global_state, "state", None)
    delay = state.delay if state else 0.0
    if delay > 0:
        time.sleep(delay)
    effective_timeout = timeout + max(delay * 2, 1.0)
    return requests.post(url, json=json, timeout=effective_timeout)


def get_with_delay(url, timeout=2):
    state = getattr(global_state, "state", None)
    delay = state.delay if state else 0.0
    if delay > 0:
        time.sleep(delay)
    effective_timeout = timeout + max(delay * 2, 1.0)
    return requests.get(url, timeout=effective_timeout)


def _serialize_neighbor(prefix: str, node: NodeInfo | None) -> dict:
    if node is None:
        return {
            f"{prefix}_id": None,
            f"{prefix}_host": None,
            f"{prefix}_socket_port": None,
        }

    return {
        f"{prefix}_id": node.node_id,
        f"{prefix}_host": node.host,
        f"{prefix}_socket_port": node.socket_port,
    }


def _send_neighbor_update(
    target: NodeInfo,
    *,
    prev=_UNSET,
    next=_UNSET,
    next_next=_UNSET,
    timeout: int = 2
):
    payload: dict = {}

    if prev is not _UNSET:
        payload.update(_serialize_neighbor("prev", prev))

    if next is not _UNSET:
        payload.update(_serialize_neighbor("next", next))

    if next_next is not _UNSET:
        payload.update(_serialize_neighbor("next_next", next_next))

    if not payload:
        return

    send_with_delay(
        f"{target.host}/update_neighbors",
        json=payload,
        timeout=timeout
    )


def _node_info_from_parts(
    node_id: int | None,
    host: str | None,
    socket_port: int | None
) -> NodeInfo | None:
    if node_id is None:
        return None

    if host is None or socket_port is None:
        return None

    try:
        port_value = int(socket_port)
    except (TypeError, ValueError):
        return None

    return NodeInfo(int(node_id), host, port_value)


def _node_info_from_dict(data: dict | None) -> NodeInfo | None:
    if not data:
        return None

    node_id = data.get("node_id")
    host = data.get("host")
    socket_port = data.get("socket_port")

    return _node_info_from_parts(node_id, host, socket_port)


def _refresh_next_successors():
    state = global_state.state

    if not state.next_node:
        state.set_next_next(None)
        return

    try:
        response = get_with_delay(f"{state.next_node.host}/health", timeout=2)
        data = response.json()
        candidate = _node_info_from_dict(data.get("next"))

        if candidate:
            state.set_next_next(candidate)
        else:
            state.set_next_next(state.self_info())
    except requests.exceptions.RequestException:
        state.set_next_next(None)
    except ValueError:
        state.set_next_next(None)


def _fetch_next_of(node: NodeInfo | None) -> NodeInfo | None:
    if not node:
        return None

    try:
        response = get_with_delay(f"{node.host}/health", timeout=2)
        data = response.json()
        return _node_info_from_dict(data.get("next"))
    except requests.exceptions.RequestException:
        return None
    except ValueError:
        return None


@router.post("/update_neighbors")
def update_neighbors(payload: dict = Body(...)):
    state = global_state.state

    prev_fields = {"prev_id", "prev_host", "prev_socket_port"}
    if any(key in payload for key in prev_fields):
        prev_id = payload.get("prev_id")

        if prev_id is None:
            state.set_prev(None)
        else:
            prev_info = _node_info_from_parts(
                prev_id,
                payload.get("prev_host"),
                payload.get("prev_socket_port")
            )
            if prev_info:
                state.set_prev(prev_info)

    next_fields = {"next_id", "next_host", "next_socket_port"}
    if any(key in payload for key in next_fields):
        next_id = payload.get("next_id")

        if next_id is None:
            state.set_next(None)
            state.set_next_next(None)
        else:
            next_info = _node_info_from_parts(
                next_id,
                payload.get("next_host"),
                payload.get("next_socket_port")
            )
            if next_info:
                state.set_next(next_info)

    next_next_fields = {"next_next_id", "next_next_host", "next_next_socket_port"}
    if any(key in payload for key in next_next_fields):
        next_next_id = payload.get("next_next_id")

        if next_next_id is None:
            state.set_next_next(None)
        else:
            nnext_info = _node_info_from_parts(
                next_next_id,
                payload.get("next_next_host"),
                payload.get("next_next_socket_port")
            )
            if nnext_info:
                state.set_next_next(nnext_info)

    _refresh_next_successors()

    logger.info(
        "Neighbors updated: prev=%s, next=%s, next_next=%s",
        state.prev_node.node_id if state.prev_node else None,
        state.next_node.node_id if state.next_node else None,
        state.next_next_node.node_id if state.next_next_node else None,
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
        state.set_next(new_node)
        state.set_prev(new_node)
        state.set_next_next(state.self_info())

        _send_neighbor_update(
            new_node,
            prev=state.self_info(),
            next=state.self_info(),
            next_next=state.self_info()
        )

        _refresh_next_successors()

        return {"message": "Joined as second node"}

    old_next = state.next_node
    state.set_next(new_node)
    state.set_next_next(old_next)

    old_next_next = _fetch_next_of(old_next) or state.self_info()

    _send_neighbor_update(
        new_node,
        prev=state.self_info(),
        next=old_next,
        next_next=old_next_next
    )

    _send_neighbor_update(
        old_next,
        prev=new_node
    )

    if state.prev_node and state.prev_node.node_id != state.node_id:
        _send_neighbor_update(
            state.prev_node,
            next_next=new_node
        )

    _refresh_next_successors()

    return {"message": "Node joined"}


@router.post("/leave")
def leave():
    state = global_state.state
    logger.info("Node leaving ring")

    try:
        if state.prev_node and state.next_node:
            _send_neighbor_update(
                state.prev_node,
                next=state.next_node
            )

            _send_neighbor_update(
                state.next_node,
                prev=state.prev_node
            )

    except Exception as e:
        logger.warning(f"Leave propagation failed: {e}")

    state.set_next(None)
    state.set_prev(None)
    state.set_next_next(None)
    state.leader_id = None
    state.in_election = False
    state.leader_node = None

    return {"message": "Left ring"}



@router.get("/health")
def health():
    state = global_state.state
    logger.info(
        "Health snapshot: status=%s leader=%s prev=%s next=%s next_next=%s",
        "alive" if state.alive else "killed",
        state.leader_id,
        state.prev_node.node_id if state.prev_node else None,
        state.next_node.node_id if state.next_node else None,
        state.next_next_node.node_id if state.next_next_node else None,
    )
    return {
        "status": "alive" if state.alive else "killed",
        "node_id": state.node_id,
        "leader_id": state.leader_id,
        "is_leader": state.leader_id == state.node_id,
        "delay": state.delay,
        "next": state.next_node.to_dict() if state.next_node else None,
        "prev": state.prev_node.to_dict() if state.prev_node else None,
        "next_next": state.next_next_node.to_dict() if state.next_next_node else None,
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

@router.get("/variable")
def get_variable():
    state = global_state.state

    if not state.alive:
        logger.info("GET /variable rejected - node killed")
        raise HTTPException(status_code=503, detail="Node is killed")

    if state.leader_node is None:
        logger.info("GET /variable rejected - no leader elected")
        return {"error": "No leader elected"}

    if state.leader_id == state.node_id:
        logger.info(
            "GET /variable served locally - value=%s",
            state.shared_value
        )
        return {
            "value": state.shared_value,
            "served_by": state.node_id
        }

    logger.info(
        "GET /variable forwarding to leader %s",
        state.leader_id
    )
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
        logger.info("POST /variable rejected - node killed")
        raise HTTPException(status_code=503, detail="Node is killed")

    if state.leader_node is None:
        logger.info("POST /variable rejected - no leader elected")
        return {"error": "No leader elected"}

    if state.leader_id == state.node_id:
        state.shared_value = value
        logger.info(
            "POST /variable applied locally - value=%s",
            value
        )
        return {
            "status": "OK",
            "value": value,
            "set_by": state.node_id
        }

    logger.info(
        "POST /variable forwarding value=%s to leader %s",
        value,
        state.leader_id
    )
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

    logger.info(
        "POST /variable acknowledged by leader %s",
        state.leader_id
    )
    return response














