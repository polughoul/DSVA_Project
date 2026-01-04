from fastapi import APIRouter, Body, HTTPException
import app.state as global_state
from app.logger import setup_logger
from app.state import NodeInfo
import requests
import time
from app.config import NODE_ID

router = APIRouter()
logger = setup_logger(NODE_ID)


# =========================
# Delay-aware send
# =========================
def send_with_delay(url, json=None, timeout=2):
    state = global_state.state
    if state.delay > 0:
        time.sleep(state.delay)
    return requests.post(url, json=json, timeout=timeout)


# =========================
# Topology helpers
# =========================
@router.post("/update_neighbors")
def update_neighbors(
    prev_id: int = Body(None),
    prev_host: str = Body(None),
    next_id: int = Body(None),
    next_host: str = Body(None),
):
    state = global_state.state

    if prev_id is not None:
        state.prev_node = NodeInfo(prev_id, prev_host)

    if next_id is not None:
        state.next_node = NodeInfo(next_id, next_host)

    logger.info(
        f"Neighbors updated: prev={state.prev_node.node_id if state.prev_node else None}, "
        f"next={state.next_node.node_id if state.next_node else None}"
    )

    return {"message": "Neighbors updated"}


def get_next_alive_node():
    state = global_state.state
    current = state.next_node
    visited = set()

    while current and current.node_id not in visited:
        visited.add(current.node_id)
        try:
            r = requests.get(f"{current.host}/health", timeout=1)
            data = r.json()

            if data["status"] == "alive":
                return current

            nxt = data.get("next")
            if not nxt:
                return None

            current = NodeInfo(nxt["node_id"], nxt["host"])
        except requests.exceptions.RequestException:
            return None

    return None


def broadcast_leader(leader_id: int):
    state = global_state.state
    current = get_next_alive_node()
    visited = set()

    while current and current.node_id not in visited:
        visited.add(current.node_id)
        try:
            send_with_delay(
                f"{current.host}/leader",
                json={"leader_id": leader_id},
                timeout=1
            )
        except requests.exceptions.RequestException:
            logger.warning("Leader broadcast failed")

        try:
            r = requests.get(f"{current.host}/health", timeout=1)
            nxt = r.json().get("next")
            if not nxt:
                break
            current = NodeInfo(nxt["node_id"], nxt["host"])
        except Exception:
            break


# =========================
# Join / Leave
# =========================
@router.post("/join")
def join(node_id: int = Body(...), host: str = Body(...)):
    state = global_state.state
    logger.info(f"Join request from node {node_id}")

    if node_id == state.node_id:
        return {"message": "Cannot join myself"}

    if state.next_node and state.next_node.node_id == node_id:
        return {"message": "Node already in ring"}

    new_node = NodeInfo(node_id, host)

    if state.next_node is None:
        state.next_node = new_node
        state.prev_node = new_node

        send_with_delay(
            f"{host}/update_neighbors",
            json={
                "prev_id": state.node_id,
                "prev_host": state.self_host,
                "next_id": state.node_id,
                "next_host": state.self_host,
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
            "next_id": old_next.node_id,
            "next_host": old_next.host,
        }
    )

    send_with_delay(
        f"{old_next.host}/update_neighbors",
        json={
            "prev_id": node_id,
            "prev_host": host,
        }
    )

    return {"message": "Node joined"}


@router.post("/leave")
def leave():
    state = global_state.state
    logger.info("Node leaving ring")

    try:
        if state.prev_node:
            send_with_delay(
                f"{state.prev_node.host}/update_neighbors",
                json={
                    "next_id": state.next_node.node_id if state.next_node else None,
                    "next_host": state.next_node.host if state.next_node else None,
                }
            )

        if state.next_node:
            send_with_delay(
                f"{state.next_node.host}/update_neighbors",
                json={
                    "prev_id": state.prev_node.node_id if state.prev_node else None,
                    "prev_host": state.prev_node.host if state.prev_node else None,
                }
            )
    except:
        pass

    state.next_node = None
    state.prev_node = None
    state.leader_id = None
    state.in_election = False

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
    logger.info("Node killed (communication disabled)")
    return {"message": "Node killed", "node_id": state.node_id}


@router.post("/revive")
def revive():
    state = global_state.state
    state.alive = True
    state.leader_id = None
    state.in_election = False
    logger.info("Node revived (communication restored)")
    return {"message": "Node revived"}


@router.post("/setDelay")
def set_delay(delay: float):
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

    next_alive = get_next_alive_node()
    if not next_alive:
        return {"error": "No alive nodes"}

    logger.info("Starting election")
    state.in_election = True

    try:
        send_with_delay(
            f"{next_alive.host}/election",
            json={"candidate_id": state.node_id}
        )
    except requests.exceptions.RequestException:
        logger.warning("Election start failed")

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
def leader(leader_id: int = Body(..., embed=True)):
    state = global_state.state

    if not state.alive:
        return {"message": "Node killed"}

    state.leader_id = leader_id
    state.in_election = False
    logger.info(f"Leader set to {leader_id}")
    return {"message": "Leader acknowledged"}


# =========================
# Shared variable
# =========================
@router.get("/variable")
def get_variable():
    state = global_state.state

    if not state.alive:
        raise HTTPException(status_code=503, detail="Node is killed")

    if state.leader_id is None:
        return {"error": "No leader elected"}

    if state.leader_id == state.node_id:
        return {"value": state.shared_value, "served_by": state.node_id}

    try:
        r = requests.get(f"{state.next_node.host}/variable", timeout=2)

        if r.status_code != 200:
            raise requests.exceptions.RequestException()

        return r.json()
    except requests.exceptions.RequestException:
        logger.warning("Leader unreachable, starting election")
        state.leader_id = None
        state.in_election = False
        start_election()
        return {"error": "Leader unreachable, election started"}


@router.post("/variable")
def set_variable(value: int = Body(..., embed=True)):
    state = global_state.state

    if not state.alive:
        raise HTTPException(status_code=503, detail="Node is killed")

    if state.leader_id is None:
        return {"error": "No leader elected"}

    if state.leader_id == state.node_id:
        state.shared_value = value
        logger.info(f"Shared variable set to {value}")
        return {"value": value, "set_by": state.node_id}

    try:
        r = send_with_delay(
            f"{state.next_node.host}/variable",
            json={"value": value}
        )
        if r.status_code != 200:
            raise requests.exceptions.RequestException()
        return r.json()
    except requests.exceptions.RequestException:
        logger.warning("Leader unreachable, starting election")
        state.leader_id = None
        state.in_election = False
        start_election()
        return {"error": "Leader unreachable, election started"}












