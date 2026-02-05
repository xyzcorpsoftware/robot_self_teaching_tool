import subprocess
import os
import traceback
import pymysql
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QCheckBox
from PyQt5.QtCore import Qt

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
    
# ✅ 패키지 import (우분투 기준)
from robot.fake_controller import FakeRobotController
from robot.fr_controller import FrRobotController
from data.points_manager import RobotPointsManager
from data.points_manager import BrewPointsManager
from usecase.brewx_service import BrewXService
from usecase.brew_service import BrewService
from ui.main_window import MainWindow

from data import db_data

"""
    Connect Dialog
    처음 시작 시 먼저 보이는 화면으로
    Robot을 실제 사용할지 설정
    Robot IP 입력 후 Connect 버튼 클릭 시 MainWindow 실행
"""

class ConnectDialog(QDialog):
    """
    - IP 입력 + Connect 버튼
    - Connect 누르면: (선택) 기존 로봇 관련 프로세스 kill -> controller 생성 -> MainWindow 띄움
    """

    # ✅ 네가 올려준 프로세스명 그대로 (systemd 서비스/노드 이름에 맞게)
    ROBOT_PROCESS_KEYWORD = "RobotSystemNode"
 
    
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("Robot Connect")
        self.resize(320, 160)

        layout = QVBoxLayout(self)

        ip_layout = QHBoxLayout()
        ip_layout.addWidget(QLabel("Robot IP:"))


        # 체크박스: 실제 로봇 사용 여부
        self.check_box = QCheckBox("Use Real Robot")
        self.check_box.setChecked(True)

        layout.addWidget(self.check_box)

        # IP 입력란
        self.edit_ip = QLineEdit()
        self.edit_ip.setPlaceholderText("예: 192.168.0.13")
        self.edit_ip.setText("192.168.0.13")
        ip_layout.addWidget(self.edit_ip)

        layout.addLayout(ip_layout)

        # Connect 버튼
        self.btn_connect = QPushButton("Connect")
        layout.addWidget(self.btn_connect, alignment=Qt.AlignCenter)

        self.btn_connect.clicked.connect(self.on_connect_clicked)

        self.main_window = None

    def _read_info_table_row_count(self):
        """
        Count rows for t_robot_info. Returns int or None on error.
        """
        conn = None
        try:
            conn = pymysql.connect(**db_data.DB_CONFIG.config)
            cursor = conn.cursor()
            sql = f"SELECT COUNT(*) FROM {db_data.DB_CONFIG.ROBOT_INFO_TABLE}"
            cursor.execute(sql)
            row = cursor.fetchone()
            return int(row[0]) if row else None
        except Exception:
            print("[CONNECT][WARN] t_robot_info column count failed:\n", traceback.format_exc())
            return None
        finally:
            if conn:
                conn.close()

    def _resolve_main_window_ui_path(self):
        """
        Always use main_window_brew.ui (UI unified)
        """
        ui_file = "main_window_brew.ui"
        resources_dir = ROOT / "resources"
        candidate = resources_dir / ui_file
        if candidate.exists():
            return str(candidate)

        print(f"[CONNECT][WARN] UI file not found: {candidate}")
        return None

    # ─────────────────────────────────────────────
    # Process kill helpers (네 코드 기반)
    # ─────────────────────────────────────────────
    def find_process(self, keyword: str):
        """
        ps aux 결과에서 keyword 포함된 라인 추출
        """
        try:
            result = subprocess.run(["ps", "aux"], stdout=subprocess.PIPE, text=True)
            processes = result.stdout.splitlines()
            matching = [p for p in processes if keyword in p and "grep" not in p]

            if matching:
                print(f"[KILL] Found processes matching '{keyword}':")
                for line in matching:
                    print("   ", line)
                return matching
            else:
                print(f"[KILL] No processes found matching '{keyword}'.")
                return []
        except Exception as e:
            print(f"[KILL][ERROR] find_process failed: {e}")
            return []

    def kill_process(self, pid: int):
        """
        kill -9 PID
        """
        try:
            subprocess.run(["kill", "-9", str(pid)], check=False)
            print(f"[KILL] Process {pid} killed.")
        except Exception as e:
            print(f"[KILL][ERROR] killing {pid} failed: {e}")

    def run_killing(self, keyword: str, max_try: int = 3):
        """
        keyword로 프로세스 찾아서 최대 max_try회 kill 시도
        """
        for _ in range(max_try):
            procs = self.find_process(keyword)
            if not procs:
                break

            # ps aux format: USER PID %CPU ...
            try:
                pid = int(procs[0].split()[1])
                self.kill_process(pid)
            except Exception as e:
                print(f"[KILL][ERROR] parse pid failed: {e}")
                break

    # ─────────────────────────────────────────────
    # Connect
    # ─────────────────────────────────────────────
    def on_connect_clicked(self):
        ip = self.edit_ip.text().strip() or "192.168.0.13"

        if os.name != "nt":
            self.run_killing(self.ROBOT_PROCESS_KEYWORD)

        row_count = self._read_info_table_row_count()
        if row_count is None:
            print("[CONNECT][WARN] t_robot_info row count is None, default to sequence mode")
            row_count = 1

        use_sequence_mode = row_count <= 1

        ui_path = self._resolve_main_window_ui_path()

        # ✅ 체크박스 상태에 따라 실제 로봇/페이크 로봇 컨트롤러 선택
        if self.check_box.isChecked():
            self.use_real_robot = True
        else:
            self.use_real_robot = False


        # ✅ 공통: controller
        controller = FrRobotController(ip=ip) if self.use_real_robot else FakeRobotController(ip=ip)
        
        # ✅ UI별로 points_manager/sequence/brew_service 분리
        if use_sequence_mode:
            # main_window.ui (기존)
            points_manager = RobotPointsManager()              # 바리스 브루X 등 기존 DB 포인트
            sequence = BrewXService(points_manager=points_manager)
            brew_service = None
        else:
            # main_window_brew.ui (브루 전용)
            points_manager = BrewPointsManager()               # 바리스 브루 전용 DB 포인트
            sequence = None                                    # brew UI에서는 sequence 안 씀
            brew_service = BrewService(points_manager=points_manager,use_real_robot=self.use_real_robot)  # ✅ 여기 중요

        self.main_window = MainWindow(
            controller=controller,
            points_manager=points_manager,
            sequence=sequence,
            brew_service=brew_service,              # ✅ 여기 중요
            component_db=db_data.DB_CONFIG.config,
            component_table=db_data.DB_CONFIG.COMPONENT_INFO_TABLE,
            ui_path=ui_path,
            use_sequence_mode=use_sequence_mode,
        )
        self.main_window.show()
        self.close()

