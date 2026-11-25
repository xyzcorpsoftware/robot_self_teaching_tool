"""Robot / rail / DB access for the new teaching tool.

Real mode reuses the old tool's modules (robot/Robot.py = FR SDK 3.9.2, robot/Rail.py, data/*).
Fake mode swaps in stand-ins with the same method names so the UI can be checked on a PC without a robot.
"""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TOOL, USER = 1, 0
GRIP_OPEN = 100          # production FRRobotConstants.GRIPPER_OPEN_POS
GRIP_CLOSE_DEFAULT = 0   # production GRIPPER_CLOSE_POS; real value comes from T_ROBOT_ATTRIBUTE.gripper_close_pos
TEACH_VEL = 30           # ponytail: one slow speed (%) for every teaching move; production cup speed is 90
JOG_VEL = 10


class MotionError(Exception):
    """Controller refused or aborted a move (collision, limit, error code)."""


class Stopped(Exception):
    """User pressed stop."""


# ───────────────────────────── robot ─────────────────────────────
class Robot:
    """Thin wrapper over the FR SDK RPC (or FakeRPC) with stop + error checks between polls."""

    def __init__(self, rpc):
        self.rpc = rpc
        self.lock = threading.Lock()   # one XML-RPC connection: keep calls short so stop() can get in
        self.stop_req = False

    @classmethod
    def connect(cls, ip, fake=False):
        if fake:
            return cls(FakeRPC())
        if os.name != "nt":
            # Same as the old tool: production's robot node must not command the robot at the same time.
            subprocess.run(["pkill", "-9", "-f", "RobotSystemNode"], check=False)
        import robot.Robot as sdk
        rpc = sdk.RPC(ip=ip)
        if not rpc.sock_cli_state_state:
            raise ConnectionError(f"no answer from {ip}")
        r = cls(rpc)
        with r.lock:
            rpc.ResetAllError()      # old tool does both on connect
            rpc.ActGripper(1, 1)
        return r

    def pose(self):
        return [float(v) for v in self.rpc.robot_state_pkg.tl_cur_pos][:6]

    def error(self):
        """(main_code, sub_code) or None. collisionState counts as an error too."""
        p = self.rpc.robot_state_pkg
        if p.main_code or p.collisionState:
            return (p.main_code, p.sub_code)
        return None

    def move(self, kind, target, vel=TEACH_VEL, acc=None, blend=0):
        """kind 'J' (target = joints) or 'L' (target = TCP). Waits until done; raises Stopped / MotionError.

        Like production send_move_*: send, then wait for motion done before the next move. blend -1 would make the
        SDK call block until arrival, so the stop button couldn't get through; it is sent as 0 instead. Same path:
        production waits for each move anyway, so a blend value never joins two moves there either.
        """
        if self.stop_req:   # stop pressed between moves (or during a gripper/rail step) must end the run
            raise Stopped()
        acc = vel if acc is None else acc
        blend = max(blend, 0)
        with self.lock:
            if kind == "J":
                ret = self.rpc.MoveJ(joint_pos=list(target), tool=TOOL, user=USER, vel=vel, acc=acc, blendT=blend)
            else:
                ret = self.rpc.MoveL(desc_pos=list(target), tool=TOOL, user=USER, vel=vel, acc=acc, blendR=blend)
        if ret != 0:
            raise MotionError(f"Move{kind} 거부 (code {ret})")
        self._wait()

    def _wait(self, timeout=60.0):
        t0 = time.monotonic()
        time.sleep(0.1)   # let the controller start the move before asking if it's done
        while True:
            if self.stop_req:
                raise Stopped()
            err = self.error()
            if err:
                raise MotionError(f"로봇이 멈췄어요 (main {err[0]}, sub {err[1]})")
            with self.lock:
                code, done = self.rpc.GetRobotMotionDone()
            if code == 0 and done == 1:
                return
            if time.monotonic() - t0 > timeout:
                raise MotionError("동작이 끝나지 않아요 (시간 초과)")
            time.sleep(0.05)

    def jog(self, axis, mm):
        p = self.pose()
        p["xyz".index(axis)] += mm
        self.move("L", p, vel=JOG_VEL)

    def gripper(self, pos, block=0):
        """block 0 = wait until the gripper finishes, 1 = return at once (production GRIPPER_NON_BLOCKING)."""
        if self.stop_req:
            raise Stopped()
        with self.lock:
            ret = self.rpc.MoveGripper(index=1, pos=pos, vel=100, force=100, maxtime=30000, block=block,
                                       type=0, rotNum=0, rotVel=0, rotTorque=0)
        if ret != 0:
            raise MotionError(f"그리퍼 오류 (code {ret})")

    def arm(self):
        """Clear a previous stop. Only the UI calls this, when the user starts a new run."""
        self.stop_req = False

    def stop(self):
        self.stop_req = True
        with self.lock:
            self.rpc.StopMove()

    def reset_error(self):
        with self.lock:
            self.rpc.ResetAllError()

    def close(self):
        try:
            self.rpc.CloseRPC()
        except Exception:
            pass


# ───────────────────────────── rail + DB ─────────────────────────────
def connect_rail(fake=False):
    """BREW only. Address like the old tool: DB T_ROBOT_INFO 'RAL' → env RAIL_IP → 192.168.0.12:2001.
    Connecting does alarm reset + servo on (RailSocket.init_sequence)."""
    if fake:
        return FakeRail()
    from data.robot_info import RobotInfoManager
    from robot.Rail import RailSocket
    ip, port = os.getenv("RAIL_IP", "192.168.0.12"), int(os.getenv("RAIL_PORT", "2001"))
    found = RobotInfoManager(table="T_ROBOT_INFO", auto_load=True).get_ip_port("RAL", default_port=port)
    if found:
        ip, port = found
    return RailSocket(ip, port, timeout=3.0, use_real_robot=True)


class Store:
    """DB points (T_ROBOT_POINTS), rail pulses (T_ROBOT_SERVICE_REQ), gripper close pos (T_ROBOT_ATTRIBUTE)."""

    def __init__(self):
        from data.points_manager import BrewPointsManager
        from data.robot_service_req import RobotServiceReqManager
        # Only DB names are read from here. Its relative points are NOT used (they drifted from production);
        # motions.py computes App/Down/Ret from production offsets.
        self.pm = BrewPointsManager()
        if not self.pm.points_dict:   # BrewPointsManager only prints DB errors
            raise ConnectionError("DB에서 좌표를 못 읽었어요")
        self.req = RobotServiceReqManager()

    def point(self, name):
        p = self.pm.get_points_by_name(name)
        if not p:
            raise KeyError(f"DB에 {name} 좌표가 없어요")
        return list(p)

    def save_point(self, name, pose):
        self.pm.update_point_in_db(name, [round(v, 3) for v in pose])

    def rail_pulse(self, cmd, n):
        v = self.req.get_rail_pos(cmd, n - 1)
        return int(v) if v not in (None, "") else None

    def save_rail(self, cmd, n, pulse):
        self.req.update_rail_pos(cmd, n, str(int(pulse)))   # update_rail_pos does no-1 itself

    def gripper_close(self):
        import pymysql
        from data.db_data import DB_CONFIG
        try:
            with pymysql.connect(**DB_CONFIG.config) as c, c.cursor() as cur:
                cur.execute("SELECT gripper_close_pos FROM T_ROBOT_ATTRIBUTE WHERE num=1")
                row = cur.fetchone()
            return int(row[0]) if row and row[0] is not None else GRIP_CLOSE_DEFAULT
        except Exception:
            return GRIP_CLOSE_DEFAULT


# ───────────────────────────── fakes (UI check without a robot) ─────────────────────────────
class _Pkg:
    def __init__(self):
        self.tl_cur_pos = [-300.0, 200.0, 400.0, 90.0, 0.0, 0.0]
        self.main_code = self.sub_code = self.collisionState = 0


class FakeRPC:
    """Mimics the SDK calls Robot uses. MoveL glides at ~300 mm/s.
    ponytail: no kinematics, so MoveJ just takes 0.8 s and leaves the shown TCP where it was."""

    def __init__(self):
        self.robot_state_pkg = _Pkg()
        self._target, self._t, self._j_until = None, None, 0.0

    def MoveL(self, desc_pos, **_):
        self._start, self._target, self._t = list(self.robot_state_pkg.tl_cur_pos), list(desc_pos), time.monotonic()
        return 0

    def MoveJ(self, joint_pos, **_):
        self._j_until = time.monotonic() + 0.8
        return 0

    def GetRobotMotionDone(self):
        if time.monotonic() < self._j_until:
            return 0, 0
        if self._target is None:
            return 0, 1
        dist = sum((a - b) ** 2 for a, b in zip(self._start[:3], self._target[:3])) ** 0.5
        k = min(1.0, (time.monotonic() - self._t) * 300 / max(dist, 1e-6))
        self.robot_state_pkg.tl_cur_pos = [a + (b - a) * k for a, b in zip(self._start, self._target)]
        if k >= 1:
            self._target = None
        return 0, int(k >= 1)

    def StopMove(self):
        self.GetRobotMotionDone()
        self._target, self._j_until = None, 0.0
        return 0

    def MoveGripper(self, block=0, **_):
        if block == 0:
            time.sleep(0.3)
        return 0

    def ResetAllError(self):
        self.robot_state_pkg.main_code = self.robot_state_pkg.sub_code = self.robot_state_pkg.collisionState = 0
        return 0

    def CloseRPC(self):
        pass


class FakeRail:
    def __init__(self):
        self.pos = 0

    def get_position_pulse(self):
        return self.pos

    def move_to_pulse_and_wait(self, target_pulse, **_):
        time.sleep(0.5)
        self.pos = int(target_pulse)
        return self.pos


# Fake BREWX uses a real store dump (bx001, 2026-11-11). ponytail: dev-PC path, override with FAKE_BREWX_SQL.
BREWX_SQL = os.getenv("FAKE_BREWX_SQL", str(Path.home() / "OneDrive/Desktop/baris-brew-station-v3/DB"
                                                       "/직영점_2026_11월11일기준/bx001_1111.sql"))


def load_sql_dump(path):
    """(points, gripper_close_pos) from a mysqldump. Same rule as production: joints if all 6 set, else TCP."""
    import re
    text = Path(path).read_text(encoding="utf-8")
    pts = {}
    rows = re.search(r"INSERT INTO `T_ROBOT_POINTS` VALUES (.*?);\s*$", text, re.M).group(1)
    for name, vals in re.findall(r"\('([^']*)',([^)]*)\)", rows):
        v = [None if x == "NULL" else float(x) for x in vals.split(",")]
        j, t = v[:6], v[6:12]
        pts[name] = j if None not in j else t
    grip = re.search(r"INSERT INTO `T_ROBOT_ATTRIBUTE` VALUES \(1,\d+,\d+,(\d+)\)", text)
    return pts, int(grip.group(1)) if grip else GRIP_CLOSE_DEFAULT


class FakeStore:
    """BREWX: points from the bx001 dump. BREW: plausible made-up numbers that only shape the screens."""

    def __init__(self, hw="BREW"):
        self.rail, self.grip = {}, GRIP_CLOSE_DEFAULT
        if hw == "BREWX":
            self.points, self.grip = load_sql_dump(BREWX_SQL)
            return
        self.points = {
            "MAC_App_J": [-250.0, 150.0, 450.0, 90.0, 0.0, 0.0],
            "MAC_App_Cup_L": [-250.0, 300.0, 450.0, 90.0, 0.0, 0.0],
            "READY_CUP_J": [-200.0, 150.0, 400.0, 90.0, 0.0, 0.0],
            "READY_APP_CUP_L": [-200.0, 300.0, 400.0, 90.0, 0.0, 0.0],
        }
        for n in range(1, 5):
            self.points[f"CUP{n}_Hold_L"] = [-250.0 + 60 * n, 480.0, 380.0, 90.0, 0.0, 0.0]
            self.points[f"CUP{n}_FAST_HOLD_L"] = [-250.0 + 60 * n, 470.0, 380.0, 90.0, 0.0, 0.0]

    def point(self, name):
        if name not in self.points:
            raise KeyError(f"DB에 {name} 좌표가 없어요")
        return list(self.points[name])

    def save_point(self, name, pose):
        self.points[name] = [round(v, 3) for v in pose]

    def rail_pulse(self, cmd, n):
        return self.rail.get((cmd, n), 0)

    def save_rail(self, cmd, n, pulse):
        self.rail[(cmd, n)] = int(pulse)

    def gripper_close(self):
        return self.grip


class FileStore(FakeStore):
    """DB stand-in for a PC without MySQL (e.g. a laptop on the real robot): points come from a mysqldump of
    THAT machine; saves go to <dump>.teach.json next to it (never the DB) and are applied again on the next start."""

    def __init__(self, sql_path):
        import json
        self.rail, (self.points, self.grip) = {}, load_sql_dump(sql_path)
        self.saved_path = Path(sql_path).with_suffix(".teach.json")
        self.saved = json.loads(self.saved_path.read_text(encoding="utf-8")) if self.saved_path.exists() else {}
        self.points.update(self.saved)

    def save_point(self, name, pose):
        import json
        super().save_point(name, pose)
        self.saved[name] = self.points[name]
        self.saved_path.write_text(json.dumps(self.saved, indent=1, ensure_ascii=False), encoding="utf-8")
