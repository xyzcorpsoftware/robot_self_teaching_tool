from typing import Protocol, List, Optional


class IRobotController(Protocol):
    def get_status(self) -> str:
        """'connected' | 'disconnected' | 'error' | 'busy'"""
        ...

    def get_tcp_pose(self) -> List[float]:
        ...

    def get_joint_pose(self) -> List[float]:
        ...

    def move_linear(self, pose: List[float], vel: float = 20, acc: float = 20, blendR: Optional[float] = None):
        ...

    def move_joint(self, joints: List[float], vel: float = 20, acc: float = 20, blendR: Optional[float] = None):
        ...

    def jog_tcp(self, direction: str, step: float = 1.0):
        ...

    def jog_joint(self, idx: int, delta: float):
        ...
