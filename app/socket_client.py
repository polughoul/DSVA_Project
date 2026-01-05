import socket
import json
import time
import app.state as global_state


def send_socket_message(host: str, port: int, message: dict, timeout=3):
    data = json.dumps(message).encode()

    state = getattr(global_state, "state", None)
    if state and state.delay > 0:
        time.sleep(state.delay)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))
            s.sendall(data)

            response = s.recv(4096).decode()
            if response:
                return json.loads(response)
    except (socket.timeout, ConnectionRefusedError, OSError) as exc:
        return {"error": "SOCKET_COMM_ERROR", "details": str(exc)}

    return None
