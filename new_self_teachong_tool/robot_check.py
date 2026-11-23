"""Read-only robot check for the new teaching tool. Sends NO motion, gripper, reset or write commands.

Checks what the planned flows depend on (FR SDK 3.9.2, robot/Robot.py):
  1. connection + real-time state (robot_state_pkg): mode, TCP/joint pose, collisionState, error codes
  2. state sample period and how often tl_cur_pos actually updates   -> "pose just before collision" log
  3. joint soft limits                                                -> limit margin in the can't-reach check
  4. IK at the current pose + how long one IK call takes              -> 5 mm path check speed

Usage (from the robot_self_teaching_tool folder):  python new_self_teachong_tool/robot_check.py [ip]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import robot.Robot as Robot  # noqa: E402  FR SDK 3.9.2

IP = sys.argv[1] if len(sys.argv) > 1 else "192.168.0.13"


def step(title, fn):
    try:
        print(f"[OK]   {title}: {fn()}")
    except Exception as e:  # keep going: one failed check should not hide the others
        print(f"[FAIL] {title}: {e!r}")


def main():
    print(f"connecting to {IP} (read-only) ...")
    r = Robot.RPC(ip=IP)
    time.sleep(1.0)  # let the state thread receive the first packets
    pkg = lambda: r.robot_state_pkg

    step("SDK version", lambda: r.GetSDKVersion())
    step("robot_mode (0=auto, 1=manual)", lambda: pkg().robot_mode)
    step("TCP pose tl_cur_pos", lambda: [round(v, 2) for v in pkg().tl_cur_pos])
    step("joint pose jt_cur_pos", lambda: [round(v, 2) for v in pkg().jt_cur_pos])
    step("collisionState (1=collision)", lambda: pkg().collisionState)
    step("error code main/sub", lambda: (pkg().main_code, pkg().sub_code))
    step("safety stop SI0/SI1", lambda: (pkg().safety_stop0_state, pkg().safety_stop1_state))
    step("state sample period (ms)", lambda: r.GetRobotRealtimeStateSamplePeriod())

    def update_rate():
        # Count how often the pose object changes over 2 s (robot may be still: also count packets via a changing field).
        seen, last, t0 = 0, None, time.time()
        while time.time() - t0 < 2.0:
            p = pkg()
            if p is not last:
                seen, last = seen + 1, p
            time.sleep(0.001)
        return f"{seen} state packets in 2 s (~{2000 / max(seen, 1):.1f} ms each)"
    step("state update rate", update_rate)

    step("joint soft limits [j1min,j1max,...]", lambda: r.GetJointSoftLimitDeg(1))

    tcp, joints = list(pkg().tl_cur_pos), list(pkg().jt_cur_pos)
    step("IK at current pose (GetInverseKinRef)", lambda: r.GetInverseKinRef(0, tcp, joints))
    step("IK has solution", lambda: r.GetInverseKinHasSolution(0, tcp, joints))
    step("FK at current joints", lambda: r.GetForwardKin(joints))

    def ik_speed(n=20):
        t0 = time.time()
        for _ in range(n):
            r.GetInverseKinRef(0, tcp, joints)
        ms = (time.time() - t0) / n * 1000
        return f"{ms:.1f} ms per call -> 100 mm path at 5 mm steps ~ {ms * 20 / 1000:.2f} s"
    step("IK call speed", ik_speed)

    try:
        r.CloseRPC()
    except Exception:
        pass
    print("done. Nothing was moved or changed.")


if __name__ == "__main__":
    main()
