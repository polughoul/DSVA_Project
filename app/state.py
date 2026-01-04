class NodeState:
    def __init__(self, node_id: int, host: str):
        self.node_id = node_id
        self.self_host = host

        self.next_node: NodeInfo | None = None
        self.prev_node: NodeInfo | None = None

        self.leader_id = None
        self.in_election = False

        self.alive = True
        self.delay = 0.0
        self.shared_value = None



state = None 

class NodeInfo:
    def __init__(self, node_id: int, host: str):
        self.node_id = node_id
        self.host = host  

    def to_dict(self):
        return {
            "node_id": self.node_id,
            "host": self.host
        }

