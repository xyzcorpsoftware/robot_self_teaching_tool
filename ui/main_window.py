import os
import re
import sys
import traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt5 import uic
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QDialog, QPushButton, QLabel, QWidget, QHBoxLayout, QVBoxLayout, QFrame
from PyQt5.QtWidgets import QInputDialog
from PyQt5.QtWidgets import QGridLayout, QGroupBox

from PyQt5.QtCore import Qt, QTimer

from ui.jog_tcp_dialog import TCPJogDialog
from ui.jog_joint_dialog import JointJogDialog
from usecase.brew_service import BrewService
import pymysql

"""
    Main Window
    Connect 이후 보이는 메인 화면
    - 버튼 이벤트 연결
    - 로봇 상태 인디케이터 표시
    - 버튼을 누를시 Jog_tcp/jont 다이얼로그 오픈
"""

class MainWindow(QDialog):
    """
    Qt Designer UI(main_window.ui)를 로드하는 메인 화면
    - 버튼 이벤트 연결
    - 로봇 상태 인디케이터 표시
    - 로봇 아이콘 클릭 시 JointJogDialog
    - 포인트 버튼 클릭 시 시퀀스 실행(있다면) 후 TCPJogDialog
    """

    def __init__(
        self,
        controller,
        points_manager=None,
        sequence=None,
        parent=None,
        ui_path=None,
        component_db=None,
        component_table=None,
        brew_service=None,
        use_sequence_mode=None,
    ):
        super().__init__(parent)

        self.controller = controller
        self.points_manager = points_manager
        self.sequence = sequence
        self.component_db = component_db
        self.component_table = component_table or "t_component_info"
        self.brew_service = brew_service
        if use_sequence_mode is None:
            self.use_sequence_mode = self.sequence is not None and self.brew_service is None
        else:
            self.use_sequence_mode = bool(use_sequence_mode)

        # 리소스 경로
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # app/
        if ui_path:
            if os.path.isabs(ui_path):
                self.ui_path = ui_path
            else:
                self.ui_path = os.path.join(base_dir, "resources", ui_path)
        else:
            self.ui_path = os.path.join(base_dir, "resources", "main_window.ui")
        self.is_brew_ui = os.path.basename(self.ui_path) == "main_window_brew.ui"
        self.image_path = os.path.join(base_dir, "resources", "image.png")

        uic.loadUi(self.ui_path, self)

        # UI 요소 찾기
        self.status_indicator: QLabel = self.findChild(QLabel, "status_indicator")
        self.lbl_status: QLabel = self.findChild(QLabel, "lbl_status")
        self.robot_label: QLabel = self.findChild(QLabel, "robot_label")

        # 이미지
        image_label: QLabel = self.findChild(QLabel, "image_label")
        if image_label:
            pixmap = QPixmap(self.image_path)
            image_label.setPixmap(pixmap)
            image_label.setScaledContents(True)

        # 상태 인디케이터 초기 스타일
        if self.status_indicator:
            self.status_indicator.setFixedSize(32, 32)
            self.status_indicator.setStyleSheet(
                "border-radius: 16px; background:#FF6B6B; border:1px solid #555;"
            )

        # 로봇 아이콘 이벤트
        if self.robot_label:
            self.robot_label.setText("ROBOT\n(Click to Jog)")
            # self.robot_label.setText("🤖")
            self.robot_label.setAlignment(Qt.AlignCenter)
            self.robot_label.installEventFilter(self)

        if not self.is_brew_ui:
            self._bind_buttons()

        if self.is_brew_ui:
            if self.brew_service is None:
                print("[BREW][WARN] brew_service is None (injected from ConnectDialog)")
            self._init_brew_ui()
        else:
            self._bind_buttons()

        # 초기 상태 갱신
        self.update_robot_state()

        # 주기적으로 상태 갱신
        self.state_timer = QTimer(self)
        self.state_timer.timeout.connect(self.update_robot_state)
        self.state_timer.start(3000)  # 3초마다

    def _bind_buttons(self):
        """
        UI에 존재하는 버튼 objectName들 연결
        """
        btn_map = {
            "btn_ice1": "ice1",
            "btn_ice2": "ice2",
            "btn_pow1": "pow1",
            "btn_pow2": "pow2",
            "btn_cof1": "cof1",
            "btn_cof2": "cof2",
            "btn_cup1": "cup1",
            "btn_cup2": "cup2",
            "btn_cup3": "cup3",
            "btn_cup4": "cup4",
            "btn_pic12": "pic12",
            "btn_pic61": "pic61",
            "btn_home": "home",
        }

        for obj_name, point_name in btn_map.items():
            btn: QPushButton = self.findChild(QPushButton, obj_name)
            if btn:
                btn.clicked.connect(lambda _, n=point_name: self.on_point_clicked(n))

    def _load_component_info_rows(self):
        if not self.component_db:
            print("[BrewUI][WARN] component_db is not set")
            return []

        conn = None
        try:
            conn = pymysql.connect(**self.component_db)
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            sql = (
                "SELECT component_cd, num, component_name, model_id, tty, baud_rate, channel_count "
                f"FROM {self.component_table}"
            )
            cursor.execute(sql)
            return list(cursor.fetchall() or [])
        except Exception:
            print("[BrewUI][WARN] load t_component_info failed:\n", traceback.format_exc())
            return []
        finally:
            if conn:
                conn.close()

    def _ensure_brew_container(self):
        container: QWidget = self.findChild(QWidget, "brew_container")
        if container is None:
            # UI에 brew_container가 없는 경우(혹시 대비)
            container = QWidget(self)
            container.setObjectName("brew_container")

        vbox = container.layout()
        if vbox is None or not isinstance(vbox, QVBoxLayout):
            vbox = QVBoxLayout(container)
            vbox.setContentsMargins(0, 10, 0, 0)
            vbox.setSpacing(10)

        if not getattr(self, "_brew_sections_built", False):
            grid = QGridLayout()
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(10)
            vbox.addLayout(grid)

            def make_group(title: str):
                gb = QGroupBox(title)
                lay = QHBoxLayout(gb)
                lay.setContentsMargins(10, 12, 10, 10)
                lay.setSpacing(8)
                return gb, lay

            self._cup_group, self._cup_row_layout = make_group("CUP")
            self._ice_group, self._ice_row_layout = make_group("ICE")
            self._coffee_group, self._coffee_row_layout = make_group("COFFEE")
            self._powder_group, self._powder_row_layout = make_group("POWDER")

            # 2x2 배치
            grid.addWidget(self._cup_group, 0, 0)
            grid.addWidget(self._ice_group, 0, 1)
            grid.addWidget(self._coffee_group, 1, 0)
            grid.addWidget(self._powder_group, 1, 1)

            # divider
            self._brew_divider = QFrame()
            self._brew_divider.setFrameShape(QFrame.HLine)
            self._brew_divider.setFrameShadow(QFrame.Plain)
            self._brew_divider.setLineWidth(2)
            self._brew_divider.setFixedHeight(24)
            self._brew_divider.setStyleSheet("background:#808080;")
            vbox.addWidget(self._brew_divider)

            # pic row
            self._pic2_row_layout = QHBoxLayout()
            self._pic2_row_layout.setSpacing(8)
            vbox.addLayout(self._pic2_row_layout)

            self._pic1_row_layout = QHBoxLayout()
            self._pic1_row_layout.setSpacing(8)
            vbox.addLayout(self._pic1_row_layout)

            self._brew_sections_built = True

        return container


    def _clear_layout(self, layout):
        if not layout:
            return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _safe_int(self, v, default=1):
        try:
            return int(v)
        except Exception:
            return default

    def _init_brew_ui(self):
        self._ensure_brew_container()

        rows = self._load_component_info_rows()
        if not rows:
            return

        # (선택) UI에 기존 고정 버튼이 있으면 숨김
        for name in (
            "btn_cup1", "btn_cup2", "btn_cup3","btn_cup4",
            "btn_ice1", "btn_ice2", 
            "btn_cof1","btn_cof2",
            "btn_pow1","btn_pow2",
            "btn_home"
        ):
            btn = self.findChild(QPushButton, name)
            if btn:
                btn.setVisible(False)

        # ✅ tty 정렬 (rows를 직접 정렬해서 overwrite 문제 제거)
        def tty_key(value: str):
            m = re.search(r"ttyS(\d+)", value)
            if m:
                return (0, int(m.group(1)))
            return (1, value)

        rows_with_tty = []
        for r in rows:
            tty = r.get("tty")
            if tty:
                rows_with_tty.append((str(tty), r))
        rows_with_tty.sort(key=lambda x: tty_key(x[0]))

        # ✅ 그룹별 spec
        group_specs = {"cup": [], "ice": [], "coffee": [], "powder": []}
        ice_index = 1
        cup_index = 1
        coffee_index = 1
        powder_index = 1

        for tty, row in rows_with_tty:
            # TTY 라벨에 따라 Component 구분
            m = re.search(r"ttyS(\d+)", tty)
            s_label = f"S{m.group(1)}" if m else tty

            component_cd = str(row.get("component_cd") or "").strip()
            comp = component_cd.lower()

            num = row.get("num", None)
            num_i = self._safe_int(num, default=1)
            component_name = row.get("component_name", "")
            tooltip = f"{component_cd} {num} {component_name}".strip()

            # CUP
            if comp == "cup":
                try:
                    channel_count = max(1, int(row.get("channel_count") or 1))
                except Exception:
                    channel_count = 1

                for _ in range(channel_count):
                    label = f"cup{cup_index}"
                    cup_index += 1
                    group_specs["cup"].append({
                        "text": label,
                        "object_name": f"btn_tty_{s_label}_{label}",
                        "tooltip": tooltip,
                        "component_cd": component_cd,
                    })

            # ICE
            elif comp == "ice":

                if num is not None:
                    label = f"ice{int(num)}"
                else:
                    label = f"ice{ice_index}"
                    ice_index += 1

                group_specs["ice"].append({
                    "text": label,
                    "object_name": f"btn_tty_{s_label}_ice",
                    "tooltip": tooltip,
                    "component_cd": component_cd,
                })

            elif comp == "cof":

                if num is not None:
                    label = f"cof{int(num)}"
                else:
                    label = f"cof{coffee_index}"
                    coffee_index += 1

                group_specs["coffee"].append({
                    "text": label,
                    "object_name": f"btn_tty_{s_label}_coffee{int(num)}",
                    "tooltip": tooltip,
                    "component_cd": component_cd,
                })
            elif comp == "pow":

                if num is not None:
                    label = f"pow{int(num)}"
                else:
                    label = f"pow{powder_index}"
                    powder_index += 1

                group_specs["powder"].append({
                    "text": label,
                    "object_name": f"btn_tty_{s_label}_powder{int(num)}",
                    "tooltip": tooltip,
                    "component_cd": component_cd,
                })
                powder_index += 1


            # else:
            #     # COF/POW만 포함
            #     if comp not in ("cof", "pow"):
            #         continue

            #     label = comp if num_i == 1 else f"{comp}{num_i}"
            #     target_group = "coffee" if comp == "cof" else "powder"

            #     group_specs[target_group].append({
            #         "text": label,
            #         "object_name": f"btn_tty_{s_label}_{label}",
            #         "tooltip": tooltip,
            #         "component_cd": component_cd,
            #     })

        # ✅ 레이아웃 clear
        self._clear_layout(self._cup_row_layout)
        self._clear_layout(self._ice_row_layout)
        self._clear_layout(self._coffee_row_layout)
        self._clear_layout(self._powder_row_layout)
        self._clear_layout(self._pic2_row_layout)
        self._clear_layout(self._pic1_row_layout)

        # ✅ 버튼 추가
        def add_buttons(row_layout, specs):
            for spec in specs:
                btn = QPushButton(spec["text"])
                btn.setObjectName(spec["object_name"])
                if spec.get("tooltip"):
                    btn.setToolTip(spec["tooltip"])
                btn.setMinimumWidth(70)
                btn.setFixedHeight(40)

                btn.clicked.connect(
                    lambda _, c=spec["component_cd"], t=spec["text"]:
                        self._on_brew_button_clicked(c, t)
                )
                row_layout.addWidget(btn)
            row_layout.addStretch(1)

        # add_buttons 호출 전에 추가
        group_specs["ice"].sort(
            key=lambda s: int(s["text"].replace("ice", "") or 0)
        )

        add_buttons(self._cup_row_layout, group_specs["cup"])
        add_buttons(self._ice_row_layout, group_specs["ice"])
        add_buttons(self._coffee_row_layout, group_specs["coffee"])
        add_buttons(self._powder_row_layout, group_specs["powder"])

        # ✅ pic/home 배치
        # pic2 라인: [stretch][HOME][stretch][pic2]
        # pic1 라인: [stretch][pic1]
        if self._pic2_row_layout is not None:
            self._pic2_row_layout.addStretch(1)

            btn_home = QPushButton("home")
            btn_home.setObjectName("btn_home_dynamic")
            btn_home.setFixedHeight(60)
            btn_home.clicked.connect(lambda _: self.go_home())
            self._pic2_row_layout.addWidget(btn_home)


            btn_move_origin = QPushButton("MoveOrigin")
            btn_move_origin.setObjectName("btn_rail_move_origin")
            # 높이는 조절 필요
            btn_move_origin.setFixedHeight(60)
            # 함수 연결 ???
            btn_move_origin.clicked.connect(lambda _: self.move_origin())
            self._pic2_row_layout.addWidget(btn_move_origin)

            self._pic2_row_layout.addStretch(1)

            btn_grip_open = QPushButton("gripper_open")
            btn_grip_open.setObjectName("btn_gripper_open")
            btn_grip_open.setFixedHeight(30)
            btn_grip_open.clicked.connect(lambda _: self.open_gripper())

            btn_grip_close = QPushButton("gripper_close")
            btn_grip_close.setObjectName("btn_gripper_close")
            btn_grip_close.setFixedHeight(30)
            btn_grip_close.clicked.connect(lambda _: self.close_gripper())

            grip_box = QVBoxLayout()
            grip_box.setSpacing(6)
            grip_box.addWidget(btn_grip_open)
            grip_box.addWidget(btn_grip_close)

            self._pic2_row_layout.addLayout(grip_box)

            self._pic2_row_layout.addStretch(1)

            btn_pic2 = QPushButton("pickupzone front")
            btn_pic2.setObjectName("btn_pic2")
            btn_pic2.setFixedHeight(40)
            btn_pic2.clicked.connect(lambda _, n="pic2": self._on_brew_button_clicked("pic", n))
            self._pic2_row_layout.addWidget(btn_pic2)

        if self._pic1_row_layout is not None:
            self._pic1_row_layout.addStretch(1)

            btn_pic1 = QPushButton("pickupzone back")
            btn_pic1.setObjectName("btn_pic1")
            btn_pic1.setFixedHeight(40)
            btn_pic1.clicked.connect(lambda _, n="pic1": self._on_brew_button_clicked("pic", n))
            self._pic1_row_layout.addWidget(btn_pic1)


    def _on_brew_button_clicked(self, component_cd: str, label: str):
        if self.use_sequence_mode:
            mapped = self._map_label_for_sequence(label)
            self.on_point_clicked(mapped)
            return
        if self.brew_service is None:
            print("[BREW][WARN] brew_service is None")
            return

        try:
            result = self.brew_service.run(component_cd, label, controller=self.controller)
            open_jog = getattr(result, "open_jog", False)
            jog_target = getattr(result, "jog_target", label)

            if isinstance(result, dict):
                open_jog = result.get("open_jog", False)
                jog_target = result.get("jog_target", label)

            if open_jog:
                self.open_tcp_jog(jog_target or label, sequence=self.brew_service)
        except Exception as e:
            print(f"[BREW][WARN] brew run failed: {e}")

    def _map_label_for_sequence(self, label: str) -> str:
        """
        Map brew UI labels to legacy main_window.ui labels.
        Legacy labels: cup1-4, ice1-2, pow1-2, cof1-2, pic12, pic61, home
        """
        if not label:
            return label

        n = str(label).strip().lower()

        # PIC mapping (brew UI -> legacy main_window.ui)
        if n == "pic1":
            return "pic12"
        if n == "pic2":
            return "pic61"

        # Direct pass-through for legacy labels
        if n in ("home", "pic12", "pic61"):
            return n

        # Pass-through for cup/ice/pow/cof with number
        for prefix in ("cup", "ice", "pow", "cof"):
            if n.startswith(prefix):
                return n

        return n

    def eventFilter(self, obj, event):
        if obj is self.robot_label and event.type() == event.MouseButtonPress:
            self.open_joint_jog()
            return True
        return super().eventFilter(obj, event)

    # ─────────────────────────────────────────
    # 상태 표시
    # ─────────────────────────────────────────
    def update_robot_state(self):
        """
        컨트롤러 상태를 읽어와 인디케이터 갱신
        """
        status = "disconnected"
        try:
            if self.controller is None:
                status = "disconnected"
            else:
                # controller.get_status() 표준을 권장
                status = self.controller.get_status()
        except Exception as e:
            print(f"[WARN] get_status failed: {e}")
            status = "error"

        self.set_robot_state(status)

    def set_robot_state(self, status: str):
        """
        connected → 초록, 나머지 → 빨강
        """
        if self.lbl_status:
            self.lbl_status.setText(status)

        if not self.status_indicator:
            return

        if status == "connected":
            color = "#7ED957"
        else:
            color = "#FF6B6B"

        size = 16
        self.status_indicator.setFixedSize(size * 2, size * 2)
        self.status_indicator.setStyleSheet(
            f"""
            QLabel {{
                background-color: {color};
                border-radius: {size}px;
                border: 1px solid #555;
            }}
            """
        )

    # ─────────────────────────────────────────
    # 버튼 클릭 → 시퀀스 → 조그
    # ─────────────────────────────────────────
    def on_point_clicked(self, name: str):
        """
        1) (가능하면) SequenceService 실행
        2) 결과에 따라 TCP Jog 오픈
        """
        # HOME 버튼은 시퀀스 없이 바로 이동 처리
        if name.lower() in ("home", "home_j"):
            self.go_home()
            return

        # SequenceService가 있으면 사용
        opened = False
        try:
            if self.sequence is not None:
                result = self.sequence.run(name, controller=self.controller)
                # result는 dict 또는 객체 둘 다 허용
                open_jog = getattr(result, "open_jog", None)
                jog_target = getattr(result, "jog_target", None)

                if isinstance(result, dict):
                    open_jog = result.get("open_jog", True)
                    jog_target = result.get("jog_target", name)

                if open_jog is False:
                    return

                if result.get("open_jog", True):
                    self.open_tcp_jog(result.get("jog_target", name))
                    opened = True

        except Exception as e:
            print(f"[WARN] sequence.run failed, fallback to jog: {e}")
        
        # 시퀀스 없으면 그냥 조그만
        if not opened:    
            self.open_tcp_jog(name)

    def open_tcp_jog(self, name: str, sequence=None):
        seq = sequence if sequence is not None else self.sequence
        dlg = TCPJogDialog(self.controller, seq, name, self)
        dlg.exec_()

    def open_joint_jog(self):
        dlg = JointJogDialog(controller=self.controller, parent=self)
        dlg.exec_()

    def go_home(self):
        """
        HOME_J로 이동. 로봇이 busy면 수행하지 않는다.
        """
        if self.controller is None:
            print("[HOME][WARN] controller is None")
            return

        try:
            if self.controller.get_status() == "busy":
                print("[HOME][WARN] robot is busy, skip home")
                return
        except Exception as e:
            print(f"[HOME][WARN] get_status failed: {e}")

        home = None
        if self.points_manager is not None and hasattr(self.points_manager, "get_points_by_name"):
            home = self.points_manager.get_points_by_name("HOME_J")
        if home is None and self.points_manager is not None:
            home = self.points_manager.points_dict.get("HOME_J")

        if home is None:
            print("[HOME][WARN] HOME_J not found in points_manager")
            return

        if hasattr(self.controller, "move_joint"):
            print("[HOME] Move to HOME_J")
            self.controller.move_joint(home, vel=40, acc=40)
        else:
            print("[HOME][WARN] controller has no move_joint")

    def open_gripper(self):
        if self.controller is None:
            print("[GRIP][WARN] controller is None")
            return
        if hasattr(self.controller, "move_gripper"):
            self.controller.move_gripper(100)
        else:
            print("[GRIP][WARN] controller has no move_gripper")

    def close_gripper(self, pos: int = None):
        if self.controller is None:
            print("[GRIP][WARN] controller is None")
            return
        if pos is None:
            pos, ok = QInputDialog.getInt(
                self,
                "Gripper Close",
                "Gripper position (0-100):",
                value=7,
                min=0,
                max=100,
            )
            if not ok:
                return
        if hasattr(self.controller, "move_gripper"):
            self.controller.move_gripper(pos)
        else:
            print("[GRIP][WARN] controller has no move_gripper")
    def move_origin(self):
        if self.controller is None:
            print("[RAIL][WARN] controller is None")
            return
        if hasattr(self.controller, "_rail_find_home"):
            self.controller._rail_find_home()
        else:
            print("[RAIL][WARN] controller has no _rail_find_home")