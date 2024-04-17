class RollingUpdateException(Exception):
    def __init__(self, message, asg_name):
        self.message = message
        self.asg_name = asg_name

class NodeNotDrainedException(Exception):
    def __init__(self, message, node_name, forced):
        self.message = message
        self.node_name = node_name
        self.forced = forced