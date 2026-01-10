import socket
import json
import threading
import app.state as global_state
from app.logger import setup_logger
from app.socket_client import send_socket_message

logger = setup_logger("socket-server")


def start_socket_server(host: str, port: int):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen()

    logger.info(f"node={global_state.state.node_id if global_state.state else '?'} server listening on {host}:{port}")

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
        logger.info(
            "node=%s incoming message type=%s from host=%s remote_port=%s payload=%s",
            state.node_id,
            message.get("type"),
            addr[0],
            addr[1],
            message
        )

        response = handle_message(message)
        if response is not None:
            conn.sendall((json.dumps(response) + "\n").encode())

    except Exception as e:
        logger.warning(
            "node=%s socket error from host=%s remote_port=%s error=%s",
            state.node_id,
            addr[0],
            addr[1],
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



def _forward_election(candidate_id: int):
    state = global_state.state

    if not state.next_node:
        logger.warning("node=%s no next node to forward election message", state.node_id)
        return {"error": "NO_NEXT_NODE"}

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
        logger.warning("node=%s election forward error", state.node_id)
        return {"error": "SOCKET_COMM_ERROR"}

    return {"status": "FORWARDED"}

def handle_election(msg: dict):
    state = global_state.state
    candidate_id = msg["candidate_id"]

    logger.info("node=%s election received candidate_id=%s", state.node_id, candidate_id)

    if not state.alive:
        logger.info("node=%s forwarding election while killed", state.node_id)
        return _forward_election(candidate_id)

    if candidate_id > state.node_id:
        forward_id = candidate_id
    elif candidate_id < state.node_id:
        forward_id = state.node_id
    else:
        state.leader_id = state.node_id
        state.leader_node = state.self_info()
        state.in_election = False

        logger.info("node=%s elected self as leader", state.node_id)

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
            logger.warning("node=%s leader broadcast failed", state.node_id)

        return {"status": "LEADER"}

    return _forward_election(forward_id)

def handle_leader(msg: dict):
    state = global_state.state

    if not state.alive:
        logger.info("node=%s ignored leader notice (node killed)", state.node_id)

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

    logger.info("node=%s leader accepted leader_id=%s", state.node_id, state.leader_id)

    if state.node_id != state.leader_id and state.next_node:
        send_socket_message(
            *state.next_node.socket_addr(),
            msg
        )

    return {"status": "OK"}




def handle_get_var():
    state = global_state.state

    if not state.alive:
        logger.info("node=%s GET_VAR rejected - node killed", state.node_id)
        return {"error": "NODE_KILLED"}

    if state.leader_id != state.node_id:
        logger.info(
            "node=%s GET_VAR redirected - not leader (current_leader=%s)",
            state.node_id,
            state.leader_id
        )
        return {
            "error": "NOT_LEADER",
            "leader_id": state.leader_id
        }

    logger.info(
        "node=%s GET_VAR served locally value=%s",
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
        logger.info("node=%s SET_VAR rejected - node killed", state.node_id)
        return {"error": "NODE_KILLED"}

    if state.leader_id != state.node_id:
        logger.info(
            "node=%s SET_VAR redirected - not leader (current_leader=%s)",
            state.node_id,
            state.leader_id
        )
        return {
            "error": "NOT_LEADER",
            "leader_id": state.leader_id
        }

    value = msg["value"]
    state.shared_value = value

    logger.info("node=%s shared variable set to %s", state.node_id, value)

    return {
        "status": "OK",
        "value": value,
        "leader_id": state.node_id
    }




