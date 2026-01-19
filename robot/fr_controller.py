from typing import List, Optional

import time
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.robot.Robot as Robot


class FrRobotController:
    """
    UI/SequenceService가 사용하는 최소 API 제공:
    - get_status()
    - get_tcp_pose(), get_joint_pose()
    - move_linear(), move_joint()
    - jog_tcp(), jog_joint()
    - (optional) save_current_tcp()
    """

    def __init__(self, ip: str = "192.168.0.13", tool: int = 1, user: int = 0):
        self.ip = ip
        self.tool = tool
        self.user = user

        self._connected = False
        self._error = False
        self._busy = False

        self.robot = None

        self.tcp_pose = [0.0] * 6
        self.joint_pose = [0.0] * 6

        self._connect()

    # ─────────────────────────────
    # connection & status
    # ─────────────────────────────
    def _connect(self):
        try:
            self.robot = Robot.RPC(ip=self.ip)
            print(f"[FR] robot connected: {self.robot}")
            self._connected = True
            self._error = False

            try:
                self.reset_all_error()
            except Exception as e:
                print(f"[FR][WARN] reset_all_error failed: {e}")
            try:
                self.send_act_gripper()
            except Exception as e:
                print(f"[FR][WARN] send_act_gripper failed: {e}")

            # 초기 pose fetch
            self.tcp_pose = self.get_tcp_pose()
            self.joint_pose = self.get_joint_pose()

        except Exception as e:
            print(f"[FR][ERROR] connect failed: {e}")
            self.robot = None
            self._connected = False
            self._error = True

    def get_status(self) -> str:
        if self._error:
            return "error"
        if not self._connected or self.robot is None:
            return "disconnected"
        if self._busy:
            return "busy"
        return "connected"

    def reset_all_error(self):
        if not self.robot:
            return
        _ = self.robot.ResetAllError()
        print("[FR] ResetAllError")

    def send_act_gripper(self):
        if not self.robot:
            return
        _ = self.robot.ActGripper(1, 1)
        print("[FR] ActGripper")

    # ─────────────────────────────
    # pose getters
    # ─────────────────────────────
    def get_tcp_pose(self) -> List[float]:
        """
        Robot SDK: ret = (code, [x,y,z,rx,ry,rz]) or int error
        """
        if not self.robot:
            return [0.0] * 6

        ret = self.robot.GetActualTCPPose()
        if isinstance(ret, int):
            if ret == -4:
                self._connected = False
                self._error = True
                print(f"[FR] Robot OFF. code={ret}")
                return [0.0] * 6
            print(f"[FR] GetActualTCPPose error: {ret}")
            self._error = True
            return [0.0] * 6

        pose = ret[1]
        pose = [round(float(v), 1) for v in pose]
        self.tcp_pose = pose
        return pose

    def get_joint_pose(self) -> List[float]:
        """
        Robot SDK: ret = (code, [j1..j6]) or int error
        """
        if not self.robot:
            return [0.0] * 6

        ret = self.robot.GetActualJointPosDegree()
        if isinstance(ret, int):
            if ret == -4:
                self._connected = False
                self._error = True
                print(f"[FR] Robot OFF. code={ret}")
                return [0.0] * 6
            print(f"[FR] GetActualJointPosDegree error: {ret}")
            self._error = True
            return [0.0] * 6

        joints = ret[1]
        joints = [round(float(v), 1) for v in joints]
        self.joint_pose = joints
        return joints

    # ─────────────────────────────
    # motion
    # ─────────────────────────────
    def move_linear(
        self,
        pose: List[float],
        vel: float = 20,
        acc: float = 20,
        blendR: Optional[float] = None,
        ovl: int = 100,
    ):
        if not self._connected or not self.robot:
            print("[FR] move_linear ignored: not connected")
            return

        if len(pose) < 6:
            print("[FR] move_linear invalid pose:", pose)
            return

        self._busy = True
        try:
            desc_pos = pose[:6]
            br = -1.0 if blendR is None else float(blendR)

            print(f"[FR] MoveL -> {desc_pos}, vel={vel}, acc={acc}, blendR={br}")
            ret = self.robot.MoveL(
                desc_pos=desc_pos,
                tool=self.tool,
                user=self.user,
                vel=float(vel),
                acc=float(acc),
                ovl=int(ovl),
                blendR=br,
                offset_flag=0,
                offset_pos=[0, 0, 0, 0, 0, 0],
            )
            print(f"[FR] MoveL ret={ret}")
        except Exception as e:
            print(f"[FR][ERROR] MoveL failed: {e}")
            self._error = True
        finally:
            self._busy = False

    def move_joint(
        self,
        joints: List[float],
        vel: float = 20,
        acc: float = 20,
        ovl: int = 100,
    ):
        if not self._connected or not self.robot:
            print("[FR] move_joint ignored: not connected")
            return

        if len(joints) < 6:
            print("[FR] move_joint invalid joints:", joints)
            return

        self._busy = True
        try:
            joint_pos = joints[:6]

            print(f"[FR] MoveJ -> {joint_pos}, vel={vel}, acc={acc}")
            ret = self.robot.MoveJ(
                joint_pos=joint_pos,
                tool=self.tool,
                user=self.user,
                vel=float(vel),
                acc=float(acc),
                ovl=int(ovl),
            )
            print(f"[FR] MoveJ ret={ret}")
        except Exception as e:
            print(f"[FR][ERROR] MoveJ failed: {e}")
            self._error = True
        finally:
            self._busy = False

    def move_gripper(self, pos: int):
        index = 1
        block = 0
        force = 100
        vel = 100
        maxtime = 30000
        type_ = 0
        rot_num = 0
        rot_vel = 0
        rot_torque = 0
        self._busy = True
        try:
            print(f"[FR] MoveGripper -> {pos}")
            ret = self.robot.MoveGripper(index=index, 
                                        pos=pos, 
                                        vel=vel, 
                                        force=force, 
                                        maxtime=maxtime, 
                                        block=block,
                                        type=type_,
                                        rotNum=rot_num,
                                        rotVel=rot_vel,
                                        rotTorque=rot_torque
)
            
            print(f"[FR] MoveGripper ret={ret}")
        except Exception as e:
            print(f"[FR][ERROR] MoveGripper failed: {e}")
            self._error = True
        finally:
            self._busy = False

    # ─────────────────────────────
    # jog
    # ─────────────────────────────
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
            print(f"[FR] jog_tcp unknown direction: {direction}")
            return

        self.move_linear(pose, vel=10, acc=10)

    def jog_joint(self, idx: int, delta: float):
        if not (0 <= idx < 6):
            print(f"[FR] jog_joint invalid idx: {idx}")
            return

        joints = self.get_joint_pose()
        joints[idx] += delta
        self.move_joint(joints, vel=10, acc=10)

    # ─────────────────────────────
    # optional helper
    # ─────────────────────────────
    def save_current_tcp(self, name: str):
        """
        UI fallback용(SequenceService 없이 저장하고 싶을 때)
        실제 DB 업데이트는 points_manager가 하니까 여기서는 로그만.
        """
        pose = self.get_tcp_pose()
        print(f"[FR] save_current_tcp {name} -> {pose}")
