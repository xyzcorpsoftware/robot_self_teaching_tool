from typing import List


class FakeRobotController:
    """
    UI 테스트용 가짜 컨트롤러
    - UI에서 요구하는 최소 API 제공
    """

    def __init__(self, ip="0.0.0.0"):
        self.ip = ip
        self._connected = True
        self._error = False
        self._busy = False

        self._tcp_pose = [100.0, 200.0, 300.0, 180.0, 0.0, 180.0]
        self._joint_pose = [0.0] * 6

        print(f"[FAKE] connected at {ip}")

    # ---------- status ----------
    def get_status(self) -> str:
        if self._error:
            return "error"
        if not self._connected:
            return "disconnected"
        if self._busy:
            return "busy"
        return "connected"

    # ---------- pose ----------
    def get_tcp_pose(self) -> List[float]:
        return list(self._tcp_pose)

    def get_joint_pose(self) -> List[float]:
        return list(self._joint_pose)

    # ---------- motion ----------
    def move_linear(self, pose: List[float], vel: float = 20, acc: float = 20, blendR=None):
        if not self._connected:
            print("[FAKE] move_linear ignored: disconnected")
            return
        self._busy = True
        self._tcp_pose = list(pose[:6])
        print(f"[FAKE] MoveL -> {self._tcp_pose} vel={vel} acc={acc} blendR={blendR}")
        self._busy = False

    def move_joint(self, joints: List[float], vel: float = 20, acc: float = 20, blendR=None):
        if not self._connected:
            print("[FAKE] move_joint ignored: disconnected")
            return
        self._busy = True
        self._joint_pose = list(joints[:6])
        print(f"[FAKE] MoveJ -> {self._joint_pose} vel={vel} acc={acc} blendR={blendR}")
        self._busy = False

    # ---------- jog ----------
    def jog_tcp(self, direction: str, step: float = 1.0):
        pose = self.get_tcp_pose()

        if direction == "x+":
            pose[0] += step
        elif direction == "x-":
            pose[0] -= step
        elif direction == "y+":
            pose[1] += step
        elif direction == "y-":
            pose[1] -= step
        elif direction == "z+":
            pose[2] += step
        elif direction == "z-":
            pose[2] -= step
        else:
            print(f"[FAKE] jog_tcp unknown direction: {direction}")
            return

        print(f"[FAKE] jog_tcp {direction} step={step} -> {pose[:3]}")
        self.move_linear(pose, vel=10, acc=10)

    def jog_joint(self, idx: int, delta: float):
        if not (0 <= idx < 6):
            print(f"[FAKE] jog_joint invalid idx: {idx}")
            return

        joints = self.get_joint_pose()
        joints[idx] += delta
        print(f"[FAKE] jog_joint J{idx+1} delta={delta} -> {joints[idx]}")
        self.move_joint(joints, vel=10, acc=10)

    # ---------- optional save helper (UI fallback용) ----------
    def save_current_tcp(self, name: str):
        pose = self.get_tcp_pose()
        print(f"[FAKE] save_current_tcp {name} -> {pose}")
