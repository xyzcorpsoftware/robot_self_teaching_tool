import subprocess
import traceback
from PyQt5.QtCore import QThread, pyqtSignal


class Ros2CliCaller(QThread):
    ok = pyqtSignal(str)      # stdout
    fail = pyqtSignal(str)    # stderr or exception

    def __init__(self, ros_setup_cmd: str, service_name: str, service_type: str, yaml_req: str,
                 timeout_sec: float = 5.0, parent=None):
        super().__init__(parent)
        self.ros_setup_cmd = ros_setup_cmd
        self.service_name = service_name
        self.service_type = service_type
        self.yaml_req = yaml_req
        self.timeout_sec = timeout_sec

    def run(self):
        try:
            bash_cmd = f"""
            set -e
            {self.ros_setup_cmd}
            ros2 service call {self.service_name} {self.service_type} "{self.yaml_req}"
            """.strip()

            res = subprocess.run(
                ["bash", "-lc", bash_cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.timeout_sec,
            )

            if res.returncode == 0:
                self.ok.emit(res.stdout.strip())
            else:
                self.fail.emit((res.stderr.strip() or res.stdout.strip() or f"returncode={res.returncode}").strip())

        except subprocess.TimeoutExpired:
            self.fail.emit(f"Timeout calling {self.service_name}")
        except Exception:
            self.fail.emit(traceback.format_exc())


def call_service_cli(
    *,
    parent,
    ros_setup_cmd: str,
    service_name: str,
    service_type: str,
    yaml_req: str,
    timeout_sec: float = 6.0,
    on_ok=None,
    on_fail=None,
    keepalive_list=None,
):
    """
    UI에서 쓰는 래퍼 함수.
    - keepalive_list: QThread GC 방지용 리스트 (ex: self._ros_threads)
    """
    th = Ros2CliCaller(
        ros_setup_cmd=ros_setup_cmd,
        service_name=service_name,
        service_type=service_type,
        yaml_req=yaml_req,
        timeout_sec=timeout_sec,
        parent=parent,
    )

    if on_ok:
        th.ok.connect(on_ok)
    if on_fail:
        th.fail.connect(on_fail)

    th.start()

    if keepalive_list is not None:
        keepalive_list.append(th)

    return th
