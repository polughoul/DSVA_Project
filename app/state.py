class NodeInfo:
    def __init__(self, node_id: int, host: str, socket_port: int):
        self.node_id = node_id
        self.host = host
        self.socket_port = socket_port

    def socket_addr(self):
        ip = self.host.replace("http://", "").split(":")[0]
        return ip, self.socket_port

    def to_dict(self):
        return {
            "node_id": self.node_id,
            "host": self.host,
            "socket_port": self.socket_port
        }


class NodeState:
    def __init__(self, node_id: int, host: str, socket_port: int | None = None):
        self.node_id = node_id
        self.self_host = host

        self.next_node: NodeInfo | None = None
        self.prev_node: NodeInfo | None = None

        self.leader_id: int | None = None
        self.leader_node: NodeInfo | None = None
        self.in_election: bool = False

        self.alive: bool = True
        self.delay: float = 0.0

        self.shared_value: int | None = None

        self.socket_port: int = socket_port if socket_port is not None else 9000 + node_id
        self.socket_alive: bool = True 

    def self_info(self) -> NodeInfo:
        return NodeInfo(self.node_id, self.self_host, self.socket_port)

state: NodeState | None = None

