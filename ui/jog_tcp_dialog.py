from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5.QtWidgets import QDialog, QGroupBox, QGridLayout, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QLabel
from PyQt5.QtCore import Qt

class TCPDispenserName:
    name_dict ={
        "cup" : ["cup1", "cup2", "cup3","cup4"],
        "coffee" : ["cof1", "cof2"],
        "powder" : ["pow1", "pow2"],
        "ice" : ["ice1", "ice2"]
    }
    sequence = None

"""
    TCP Jog Dialog
    로봇이 해당 버튼에 연결된 디스펜서로 이동한 뒤
    X,Y,Z 축을 세밀하게 조정하고
    저장할 수 있는 다이얼로그

"""
class TCPJogDialog(QDialog):
    """
    TCP 조그 다이얼로그
    - X/Y, Z 조그
    - Saved: target_name 포인트로 저장 요청
    - cup1/2/3일 때 Cup Extract 버튼 예시 포함
    """

    def __init__(self, controller, sequence, target_name: str, parent=None):
        super().__init__(parent)   # ❗ 반드시 제일 먼저

        self.controller = controller
        self.sequence = sequence
        self.target_name = target_name
        self.rail_msg = None
        self.dp_name_class = TCPDispenserName()
        self.dp_name_class.sequence = sequence
        print(type(self.dp_name_class.sequence))
        self.rail_position = self.dp_name_class.sequence.RAIL_TARGET_PULSE.get(target_name, 0)
        
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
        # current_pos_label.setFrameStyle(QLabel.Panel | QLabel.Sunken)
        current_pos_label.setLineWidth(2)
        current_pos_label.setMargin(5)
        current_pos_label.setWordWrap(True)
        right_layout.addWidget(current_pos_label)
        self.rail_msg = QLineEdit(str(self.rail_position))
        self.rail_msg.setAlignment(Qt.AlignCenter)
        
        right_layout.addWidget(self.rail_msg)

        # rail_position.setAlignment(Qt.AlignCenter)

        btn_rail_start = QPushButton("Rail Move Start")
        right_layout.addWidget(btn_rail_start)
        btn_rail_start.clicked.connect(self.rail_move_start)
        
        
        # cup 계열일 때만 표시되는 추가 버튼 (예시)
        if self.target_name in TCPDispenserName.name_dict["cup"]:
            btn_cup_extra = QPushButton("Cup Extract")
            right_layout.addWidget(btn_cup_extra)
            btn_cup_extra.clicked.connect(self._on_cup_extra_clicked)

        if self.target_name in TCPDispenserName.name_dict["coffee"]:
            btn_coffee_extra = QPushButton("Coffee Extract")
            right_layout.addWidget(btn_coffee_extra)
            btn_coffee_extra.clicked.connect(self._on_coffee_extra_clicked)
        if self.target_name in TCPDispenserName.name_dict["ice"]:
            btn_ice_extra = QPushButton("Ice Extract")
            right_layout.addWidget(btn_ice_extra)
            btn_ice_extra.clicked.connect(self._on_ice_extra_clicked)
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
            
            if self.rail_position != self.rail_msg.text():
                self.rail_position = self.rail_msg.text()
                # self.sequence.save_pulse(self.target_name, self.rail_position)
        except Exception as e:
            print(f"[ERROR] save failed: {e}")
        finally:
            self.accept()

    def _on_cup_extra_clicked(self):
        if self.sequence and hasattr(self.sequence, "cup_extract_async"):
            self.sequence.cup_extract_async(self.target_name)
        print(f"[UI] Extra button clicked for {self.target_name}")
    def _on_coffee_extra_clicked(self):
        if self.sequence and hasattr(self.sequence, "coffee_extract_async"):
            self.sequence.coffee_extract_async(self.target_name)
        print(f"[UI] Extra button clicked for {self.target_name}")
    def _on_ice_extra_clicked(self):
        if self.sequence and hasattr(self.sequence, "ice_extract_async"):
            self.sequence.ice_extract_async(self.target_name)
        print(f"[UI] Extra button clicked for {self.target_name}")
    def _on_powder_extra_clicked(self):
        if self.sequence and hasattr(self.sequence, "powder_dispense_async"):
            self.sequence.powder_dispense_async(self.target_name)
        print(f"[UI] Extra button clicked for {self.target_name}")

    def rail_move_start(self):
    
        if self.rail_position != self.rail_msg.text():
            self.rail_position = self.rail_msg.text()
        
        if self.sequence and hasattr(self.sequence, "rail_move_async"):
            self.sequence.rail_move_async(self.target_name, self.rail_position, controller=self.controller)
        print(f"[UI] Rail Move Start clicked for {self.target_name} to position {self.rail_position}")

    def closeEvent(self, event):
        """
        X 버튼으로 조그 창을 닫을 때 저장된 복귀 모션을 실행한다.
        SequenceService에 반환 모션 헬퍼가 있으면 활용한다.
        """
        try:
            if self.sequence and hasattr(self.sequence, "_return_motion_after_save"):
                # target_name을 실제 포인트명으로 변환해 복귀 수행
                if hasattr(self.sequence, "_resolve_saved_point_name"):
                    target = self.sequence._resolve_saved_point_name(self.target_name)
                else:
                    target = self.target_name
                self.sequence._return_motion_after_save(
                    target,
                    controller=self.controller
                )
        except Exception as e:
            print(f"[UI][WARN] closeEvent return failed: {e}")
        super().closeEvent(event)

