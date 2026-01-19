from PyQt5.QtWidgets import QDialog, QGroupBox, QGridLayout, QVBoxLayout, QPushButton, QLabel
from PyQt5.QtCore import Qt


class JointJogDialog(QDialog):
    """
    Joint Jog 다이얼로그
    - J1~J6
    - 각 조인트: [-] [값] [+]
    - 버튼 길게 누르면 반복 조그
    """

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Joint Jog")

        self.joint_labels = []
        self._build_ui()
        self.refresh_joint_labels()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)

        group = QGroupBox("Joint Jog (J1 ~ J6)")
        grid = QGridLayout()
        grid.setHorizontalSpacing(15)
        grid.setVerticalSpacing(8)

        step_deg = 1.0

        for i in range(6):
            joint_name = f"J{i+1}"

            lbl_name = QLabel(joint_name)
            lbl_name.setAlignment(Qt.AlignCenter)

            btn_minus = QPushButton("-")
            btn_plus = QPushButton("+")
            btn_minus.setFixedWidth(36)
            btn_plus.setFixedWidth(36)

            # 누르고 있으면 계속 조그
            for btn in (btn_minus, btn_plus):
                btn.setAutoRepeat(True)
                btn.setAutoRepeatDelay(250)
                btn.setAutoRepeatInterval(80)

            lbl_value = QLabel("0.00")
            lbl_value.setAlignment(Qt.AlignCenter)
            lbl_value.setFixedWidth(70)

            row = i
            grid.addWidget(lbl_name, row, 0)
            grid.addWidget(btn_minus, row, 1)
            grid.addWidget(lbl_value, row, 2)
            grid.addWidget(btn_plus, row, 3)

            btn_minus.clicked.connect(lambda _, idx=i: self.on_jog_clicked(idx, -step_deg))
            btn_plus.clicked.connect(lambda _, idx=i: self.on_jog_clicked(idx, +step_deg))

            self.joint_labels.append(lbl_value)

        group.setLayout(grid)
        main_layout.addWidget(group)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        main_layout.addWidget(btn_close, alignment=Qt.AlignRight)

    def on_jog_clicked(self, idx: int, delta: float):
        try:
            if self.controller is None:
                return
            self.controller.jog_joint(idx, delta)
        except Exception as e:
            print(f"[ERROR] jog_joint failed: {e}")

        self.refresh_joint_labels()

    def refresh_joint_labels(self):
        joints = [0.0] * 6
        try:
            if self.controller is None:
                joints = [0.0] * 6
            elif hasattr(self.controller, "get_joint_pose"):
                joints = self.controller.get_joint_pose()
            elif hasattr(self.controller, "get_joints"):
                joints = self.controller.get_joints()
            else:
                joints = getattr(self.controller, "joints", [0.0] * 6)
        except Exception as e:
            print(f"[WARN] get_joint_pose failed: {e}")
            joints = [0.0] * 6

        for i, lbl in enumerate(self.joint_labels):
            if i < len(joints):
                lbl.setText(f"{float(joints[i]):.2f}")
