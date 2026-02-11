# ui/tcp_jog_dialog.py
from PyQt5.QtWidgets import (
    QDialog, QGroupBox, QGridLayout, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel
)
from PyQt5.QtCore import Qt

# ✅ ros 폴더 헬퍼 import
from ros import (
    call_service_cli,
    make_seq_no,
    infer_channel_from_target_name,
    yaml_cup,
    yaml_coffee,
    yaml_ice,
    yaml_powder,
)


class TCPDispenserName:
    name_dict ={
        "cup" : ["cup1", "cup2", "cup3", "cup4"],
        "coffee" : ["cof1", "cof2"],
        "powder" : ["pow1", "pow2"],
        "ice" : ["ice1", "ice2"]
    }
    sequence = None


# =========================================================
# ✅ 서비스 설정 (너가 확정해준 값)
# =========================================================
SVC_CUP  = "/cup/service"
TYPE_CUP = "message/srv/CupService"

SVC_COFFEE  = "/coffee/service"
TYPE_COFFEE = "message/srv/CoffeeService"

SVC_ICE  = "/ice/service"
TYPE_ICE = "message/srv/IceService"

SVC_POWDER  = "/powder/service"
TYPE_POWDER = "message/srv/PowderService"

# ✅ ROS 환경 source
ROS_SETUP_CMD = "source /opt/ros/humble/setup.bash && source ~/BB3_ROS_WS/install/setup.bash"
# =========================================================


class TCPJogDialog(QDialog):
    """
    TCP 조그 다이얼로그
    - X/Y, Z 조그
    - Saved: target_name 포인트 저장 요청
    - cup/coffee/ice/powder 버튼 클릭 시 ROS2 service call (CLI) 실행
    """

    def __init__(self, controller, sequence, target_name: str, parent=None):
        super().__init__(parent)

        self.controller = controller
        self.sequence = sequence
        self.target_name = target_name

        self.rail_msg = None
        self.dp_name_class = TCPDispenserName()
        self.dp_name_class.sequence = sequence

        # ✅ rail position 초기값
        self.rail_position = 0
        try:
            self.rail_position = self.dp_name_class.sequence.RAIL_TARGET_PULSE.get(target_name, 0)
        except Exception:
            self.rail_position = 0

        # ✅ QThread GC 방지 리스트
        self._ros_threads = []

        self.setWindowTitle(f"TCP Jog - {target_name}")
        self._build_ui()

    def _build_ui(self):
        main = QHBoxLayout(self)

        # X/Y 그룹
        xy_group = QGroupBox("X / Y")
        xy_layout = QGridLayout()
        btn_y_p = QPushButton("+Y")
        btn_y_m = QPushButton("-Y")
        btn_x_p = QPushButton("+X")
        btn_x_m = QPushButton("-X")
        xy_layout.addWidget(btn_y_p, 0, 1)
        xy_layout.addWidget(btn_x_m, 1, 0)
        xy_layout.addWidget(btn_x_p, 1, 2)
        xy_layout.addWidget(btn_y_m, 2, 1)
        xy_group.setLayout(xy_layout)

        # Z 그룹
        z_group = QGroupBox("Z")
        z_layout = QVBoxLayout()
        btn_z_p = QPushButton("+Z")
        btn_z_m = QPushButton("-Z")
        z_layout.addWidget(btn_z_p)
        z_layout.addWidget(btn_z_m)
        z_group.setLayout(z_layout)

        # 오른쪽 버튼 영역
        right_layout = QVBoxLayout()
        right_layout.addStretch()

        current_pos_label = QLabel(text=f'Current DP \n\n {self.target_name.upper()}')
        current_pos_label.setAlignment(Qt.AlignCenter)
        current_pos_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        current_pos_label.setFixedHeight(70)
        current_pos_label.setFixedWidth(150)
        current_pos_label.setLineWidth(2)
        current_pos_label.setMargin(5)
        current_pos_label.setWordWrap(True)
        right_layout.addWidget(current_pos_label)

        self.rail_msg = QLineEdit(str(self.rail_position))
        self.rail_msg.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(self.rail_msg)

        btn_rail_start = QPushButton("Rail Move Start")
        right_layout.addWidget(btn_rail_start)
        btn_rail_start.clicked.connect(self.rail_move_start)

        # ✅ cup 계열
        if self.target_name in TCPDispenserName.name_dict["cup"]:
            btn_cup_extra = QPushButton("Cup Extract")
            right_layout.addWidget(btn_cup_extra)
            btn_cup_extra.clicked.connect(self._on_cup_extra_clicked)

        # ✅ coffee 계열
        if self.target_name in TCPDispenserName.name_dict["coffee"]:
            btn_coffee_extra = QPushButton("Coffee Extract")
            right_layout.addWidget(btn_coffee_extra)
            btn_coffee_extra.clicked.connect(self._on_coffee_extra_clicked)

        # ✅ ice 계열
        if self.target_name in TCPDispenserName.name_dict["ice"]:
            btn_ice_extra = QPushButton("Ice Extract")
            right_layout.addWidget(btn_ice_extra)
            btn_ice_extra.clicked.connect(self._on_ice_extra_clicked)

        # ✅ powder 계열
        if self.target_name in TCPDispenserName.name_dict["powder"]:
            btn_powder_extra = QPushButton("Powder Extract")
            right_layout.addWidget(btn_powder_extra)
            btn_powder_extra.clicked.connect(self._on_powder_extra_clicked)

        btn_save = QPushButton("Saved")
        right_layout.addWidget(btn_save)

        main.addWidget(xy_group)
        main.addWidget(z_group)
        main.addLayout(right_layout)

        # 조그 연결
        step = 1.0
        btn_x_p.clicked.connect(lambda: self._jog("x+", step))
        btn_x_m.clicked.connect(lambda: self._jog("x-", step))
        btn_y_p.clicked.connect(lambda: self._jog("y+", step))
        btn_y_m.clicked.connect(lambda: self._jog("y-", step))
        btn_z_p.clicked.connect(lambda: self._jog("z+", step))
        btn_z_m.clicked.connect(lambda: self._jog("z-", step))
        btn_save.clicked.connect(self._on_save)

    def _jog(self, direction: str, step: float):
        if self.sequence is None:
            return

        self.sequence.jog_tcp(
            ui_point_name=self.target_name,
            direction=direction,
            step=step,
            controller=self.controller
        )

    def _on_save(self):
        """
        저장 우선순위:
        1) sequence.save_point(target_name, controller) 제공되면 그걸 사용
        2) controller.save_current_tcp(target_name) 제공되면 그걸 사용
        """
        try:
            if self.sequence is not None and hasattr(self.sequence, "save_point"):
                self.sequence.save_point(self.target_name, controller=self.controller)
            elif self.controller is not None and hasattr(self.controller, "save_current_tcp"):
                self.controller.save_current_tcp(self.target_name)
            else:
                print("[WARN] No save handler. Implement sequence.save_point() or controller.save_current_tcp()")

            # rail 저장
            try:
                self.sequence.save_pulse(self.target_name, int(self.rail_position))
                self.dp_name_class.sequence.RAIL_TARGET_PULSE[self.target_name] = int(self.rail_position)
            except Exception as e:
                print(f"[WARN] save_pulse failed: {e}")

        except Exception as e:
            print(f"[ERROR] save failed: {e}")
        finally:
            self.accept()

    def rail_move_start(self):
        txt = self.rail_msg.text().strip()
        if txt:
            self.rail_position = int(float(txt))

        if self.sequence and hasattr(self.sequence, "rail_move_async"):
            self.sequence.rail_move_async(self.target_name, self.rail_position, controller=self.controller)

        print(f"[UI] Rail Move Start clicked for {self.target_name} to position {self.rail_position}")

    def closeEvent(self, event):
        try:
            if self.sequence and hasattr(self.sequence, "_return_motion_after_save"):
                if hasattr(self.sequence, "_resolve_saved_point_name"):
                    target = self.sequence._resolve_saved_point_name(self.target_name)
                else:
                    target = self.target_name
                self.sequence._return_motion_after_save(target, controller=self.controller)
        except Exception as e:
            print(f"[UI][WARN] closeEvent return failed: {e}")
        super().closeEvent(event)

    # =========================================================
    # ✅ ROS2 CLI 호출 버튼 4개
    # =========================================================
    def _on_cup_extra_clicked(self):
        channel = infer_channel_from_target_name(self.target_name)
        seq_no = make_seq_no("cup")
        cmd = "EXTRACT"   # ✅ 네 cmd 규격에 맞게 변경

        y = yaml_cup(seq_no, cmd, channel)

        call_service_cli(
            parent=self,
            ros_setup_cmd=ROS_SETUP_CMD,
            service_name=SVC_CUP,
            service_type=TYPE_CUP,
            yaml_req=y,
            timeout_sec=6.0,
            on_ok=lambda out: print("[ROS2][OK][CUP]\n", out),
            on_fail=lambda err: print("[ROS2][FAIL][CUP]\n", err),
            keepalive_list=self._ros_threads,
        )

    def _on_coffee_extra_clicked(self):
        seq_no = make_seq_no("cof")
        cmd = "EXTRACT"      # ✅ 변경 가능
        protocol_id = 1      # ✅ 실제 규격값 넣기
        device_id = 1        # ✅ 실제 규격값 넣기
        delay_time = 0.0

        y = yaml_coffee(seq_no, cmd, protocol_id, device_id, delay_time)

        call_service_cli(
            parent=self,
            ros_setup_cmd=ROS_SETUP_CMD,
            service_name=SVC_COFFEE,
            service_type=TYPE_COFFEE,
            yaml_req=y,
            timeout_sec=8.0,
            on_ok=lambda out: print("[ROS2][OK][COFFEE]\n", out),
            on_fail=lambda err: print("[ROS2][FAIL][COFFEE]\n", err),
            keepalive_list=self._ros_threads,
        )

    def _on_ice_extra_clicked(self):
        channel = infer_channel_from_target_name(self.target_name)
        seq_no = make_seq_no("ice")
        cmd = "DISPENSE"   # ✅ 변경 가능
        ice_qty = 1        # ✅ 필요하면 UI 입력값으로 교체
        water_qty = 0

        y = yaml_ice(seq_no, cmd, ice_qty, water_qty, channel)

        call_service_cli(
            parent=self,
            ros_setup_cmd=ROS_SETUP_CMD,
            service_name=SVC_ICE,
            service_type=TYPE_ICE,
            yaml_req=y,
            timeout_sec=8.0,
            on_ok=lambda out: print("[ROS2][OK][ICE]\n", out),
            on_fail=lambda err: print("[ROS2][FAIL][ICE]\n", err),
            keepalive_list=self._ros_threads,
        )

    def _on_powder_extra_clicked(self):
        channel = infer_channel_from_target_name(self.target_name)
        seq_no = make_seq_no("pow")
        cmd = "DISPENSE"    # ✅ 변경 가능
        part_no = 1         # ✅ 실제 규격값
        menu_id = "BR00"    # ✅ 실제 menu_id로 연결 가능
        opt_id = "0"
        req_value = 1       # ✅ 실제 규격값

        y = yaml_powder(seq_no, cmd, part_no, menu_id, opt_id, channel, req_value)

        call_service_cli(
            parent=self,
            ros_setup_cmd=ROS_SETUP_CMD,
            service_name=SVC_POWDER,
            service_type=TYPE_POWDER,
            yaml_req=y,
            timeout_sec=8.0,
            on_ok=lambda out: print("[ROS2][OK][POWDER]\n", out),
            on_fail=lambda err: print("[ROS2][FAIL][POWDER]\n", err),
            keepalive_list=self._ros_threads,
        )
