import sys
import re
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QPushButton, QFrame, QLabel
)
from PyQt5.QtCore import Qt


class BrewDemoWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Brew UI Demo (CUP / ICE / COFFEE / POWDER)")
        self.resize(900, 420)

        # 메인 중앙 위젯
        root = QWidget(self)
        self.setCentralWidget(root)
        self.root_vbox = QVBoxLayout(root)
        self.root_vbox.setContentsMargins(20, 20, 20, 20)
        self.root_vbox.setSpacing(12)

        # 상단 안내
        self.root_vbox.addWidget(QLabel("DB 없이 하드코딩 rows로 버튼 생성 (클릭하면 콘솔 출력)"))

        # brew_container (네 코드에서 findChild로 찾는 대상)
        self.brew_container = QWidget(self)
        self.brew_container.setObjectName("brew_container")
        self.root_vbox.addWidget(self.brew_container)

        # 초기화
        self._init_brew_ui()

    # ---------------------------
    # Helper (네 코드 스타일 유지)
    # ---------------------------
    def _safe_int(self, value, default=1):
        try:
            return int(value)
        except Exception:
            return default

    def _clear_layout(self, layout):
        if not layout:
            return
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _on_brew_button_clicked(self, component_cd, text, rail_pulse=None):
            msg = f"[CLICK] component_cd={component_cd}, text={text}, rail_pulse={rail_pulse}"
            print(msg)
            if hasattr(self, "statusBar") and self.statusBar():
                self.statusBar().showMessage(msg, 5000)  # 5초 표시

    # ---------------------------
    # ✅ DB 대신 하드코딩 rows
    # (네 INSERT 기반)
    # ---------------------------
    def _load_component_info_rows(self):
        # DB에서 DictCursor로 가져오는 형태와 동일하게 dict list로 구성
        return [
            {"component_cd": "ICE", "num": 1, "component_name": "제빙기", "model_id": "ICEVAN", "tty": "/dev/ttyS4", "baud_rate": 9600, "channel_count": 1},
            {"component_cd": "ICE", "num": 2, "component_name": "제빙기", "model_id": "ICEVAN", "tty": "/dev/ttyS3", "baud_rate": 9600, "channel_count": 1},
            {"component_cd": "COF", "num": 1, "component_name": "커피머신", "model_id": "EVERSYS", "tty": "/dev/ttyS2", "baud_rate": 115200, "channel_count": 1},
            {"component_cd": "POW", "num": 1, "component_name": "XYZ POWDER DP", "model_id": "XYZ", "tty": "/dev/ttyS1", "baud_rate": 115200, "channel_count": 8},
            {"component_cd": "CUP", "num": 1, "component_name": "XYZ CUP DP", "model_id": "XYZ", "tty": "/dev/ttyS0", "baud_rate": 115200, "channel_count": 2},
            {"component_cd": "SYS", "num": 1, "component_name": "XYZ", "model_id": "XYZ", "tty": None, "baud_rate": None, "channel_count": 1},
            {"component_cd": "ROB", "num": 1, "component_name": "XYZ", "model_id": "XYZ", "tty": None, "baud_rate": None, "channel_count": 1},
            {"component_cd": "VIS", "num": 1, "component_name": "XYZ vision", "model_id": "XYZ", "tty": None, "baud_rate": None, "channel_count": 1},
            {"component_cd": "PIC", "num": 1, "component_name": "XYZ Pickup zone", "model_id": "XYZ", "tty": None, "baud_rate": None, "channel_count": 1},
            {"component_cd": "VOI", "num": 1, "component_name": "XYZ Voice", "model_id": "XYZ", "tty": None, "baud_rate": None, "channel_count": 1},
            {"component_cd": "CUP", "num": 2, "component_name": "XYZ CUP DP", "model_id": "XYZ", "tty": "/dev/ttyS5", "baud_rate": 115200, "channel_count": 2},
        ]

    # ---------------------------
    # ✅ 4개 영역 생성
    # ---------------------------
    def _ensure_brew_container(self):
        container = self.findChild(QWidget, "brew_container")
        if container is None:
            container = self.brew_container  # 데모에서는 이미 만들어둠

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
                gb.setAlignment(Qt.AlignLeft)
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

            # pic row (원래 코드 느낌 유지)
            self._pic2_row_layout = QHBoxLayout()
            self._pic2_row_layout.setSpacing(8)
            vbox.addLayout(self._pic2_row_layout)

            self._pic1_row_layout = QHBoxLayout()
            self._pic1_row_layout.setSpacing(8)
            vbox.addLayout(self._pic1_row_layout)

            self._brew_sections_built = True

        return container

    # ---------------------------
    # ✅ 버튼 생성 (네 기존 규칙 기반)
    # ---------------------------
    def _init_brew_ui(self):
        self._ensure_brew_container()

        rows = self._load_component_info_rows()
        if not rows:
            return

        # ✅ tty 정렬
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
        cup_index = 1  # ✅ CUP 연속 번호

        for tty, row in rows_with_tty:
            m = re.search(r"ttyS(\d+)", tty)
            s_label = f"S{m.group(1)}" if m else tty

            component_cd = str(row.get("component_cd") or "").strip()
            comp = component_cd.lower()

            num = row.get("num", None)
            num_i = self._safe_int(num, default=1)
            component_name = row.get("component_name", "")
            tooltip_base = f"{component_cd} {num} {component_name}".strip()

            # CUP channel_count
            if comp == "cup":
                try:
                    channel_count = max(1, int(row.get("channel_count") or 1))
                except Exception:
                    channel_count = 1

                for _ in range(channel_count):
                    label = f"cup{cup_index}"
                    cup_index += 1

                    pulse = getattr(self, "RAIL_TARGET_PULSE", {}).get(label)
                    tooltip = tooltip_base if pulse is None else f"{tooltip_base}\nRAIL_PULSE: {pulse}"

                    group_specs["cup"].append({
                        "text": label,
                        "object_name": f"btn_tty_{s_label}_{label}",
                        "tooltip": tooltip,
                        "component_cd": component_cd,
                        "rail_pulse": pulse,
                    })

            elif comp == "ice":
                ICE_LABEL_MAP = {1: 2, 2: 1}  # 예: ICE num=1을 ice2로, num=2를 ice1로

                if num is not None:
                    mapped = ICE_LABEL_MAP.get(int(num), int(num))
                    label = f"ice{mapped}"
                else:
                    label = f"ice{ice_index}"
                    ice_index += 1

                pulse = getattr(self, "RAIL_TARGET_PULSE", {}).get(label)
                tooltip = tooltip_base if pulse is None else f"{tooltip_base}\nRAIL_PULSE: {pulse}"

                group_specs["ice"].append({
                    "text": label,
                    "object_name": f"btn_tty_{s_label}_ice",
                    "tooltip": tooltip,
                    "component_cd": component_cd,
                    "rail_pulse": pulse,
                })

            else:
                # COF/POW만 포함 (그 외 SYS/ROB/VIS/VOI/PIC는 제외)
                if comp not in ("cof", "pow"):
                    continue

                label = comp if num_i == 1 else f"{comp}{num_i}"
                target_group = "coffee" if comp == "cof" else "powder"

                pulse = getattr(self, "RAIL_TARGET_PULSE", {}).get(label)
                tooltip = tooltip_base if pulse is None else f"{tooltip_base}\nRAIL_PULSE: {pulse}"

                group_specs[target_group].append({
                    "text": label,
                    "object_name": f"btn_tty_{s_label}_{label}",
                    "tooltip": tooltip,
                    "component_cd": component_cd,
                    "rail_pulse": pulse,
                })

        # ✅ 4개 레이아웃 clear
        self._clear_layout(self._cup_row_layout)
        self._clear_layout(self._ice_row_layout)
        self._clear_layout(self._coffee_row_layout)
        self._clear_layout(self._powder_row_layout)

        # pic 레이아웃도 있으면 clear
        if getattr(self, "_pic2_row_layout", None):
            self._clear_layout(self._pic2_row_layout)
        if getattr(self, "_pic1_row_layout", None):
            self._clear_layout(self._pic1_row_layout)

        # ✅ 버튼 추가 헬퍼
        def add_buttons(row_layout, specs):
            for spec in specs:
                pulse = spec.get("rail_pulse")

                # ✅ 버튼에서 레일값이 '눈에 보이게' 표시
                if pulse is None:
                    display_text = spec["text"]
                else:
                    display_text = f'{spec["text"]}\n({pulse})'   # 2줄 표시

                btn = QPushButton(display_text)
                btn.setObjectName(spec["object_name"])

                if spec.get("tooltip"):
                    btn.setToolTip(spec["tooltip"])

                btn.setMinimumWidth(90)   # 숫자까지 보이게 약간 키움
                btn.setFixedHeight(52)    # 2줄이라 높이 증가

                btn.setProperty("rail_pulse", pulse)

                btn.clicked.connect(
                    lambda _, c=spec["component_cd"], t=spec["text"], p=pulse:
                        self._on_brew_button_clicked(c, t, p)
                )
                row_layout.addWidget(btn)
            row_layout.addStretch(1)

        add_buttons(self._cup_row_layout, group_specs["cup"])
        add_buttons(self._ice_row_layout, group_specs["ice"])
        add_buttons(self._coffee_row_layout, group_specs["coffee"])
        add_buttons(self._powder_row_layout, group_specs["powder"])

        # ✅ pic 버튼은 기존 데모처럼 아래에 (원하면 제거 가능)
        # ✅ pic 배치: pic2 라인 = HOME 가운데 + pic2 오른쪽
#            pic1 라인 = pic1 오른쪽 (세로 유지)
        pic2_layout = getattr(self, "_pic2_row_layout", None)
        pic1_layout = getattr(self, "_pic1_row_layout", None)

        # --- pic2 라인 ---
        if pic2_layout is not None:
            # [stretch][HOME][stretch][pic2]
            pic2_layout.addStretch(1)

            # HOME(가운데)
            home_pulse = getattr(self, "RAIL_TARGET_PULSE", {}).get("home")
            btn_home = QPushButton("home")
            btn_home.setObjectName("btn_home")
            btn_home.setFixedHeight(40)
            if home_pulse is not None:
                btn_home.setToolTip(f"RAIL_PULSE: {home_pulse}")
            btn_home.setProperty("rail_pulse", home_pulse)
            btn_home.clicked.connect(lambda _, n="home", p=home_pulse: self._on_brew_button_clicked("HOME", n, p))
            pic2_layout.addWidget(btn_home)

            pic2_layout.addStretch(1)

            # pic2(오른쪽)
            pic2_pulse = getattr(self, "RAIL_TARGET_PULSE", {}).get("pic2")
            btn_pic2 = QPushButton("pic2")
            btn_pic2.setObjectName("btn_pic2")
            btn_pic2.setFixedHeight(40)
            if pic2_pulse is not None:
                btn_pic2.setToolTip(f"RAIL_PULSE: {pic2_pulse}")
            btn_pic2.setProperty("rail_pulse", pic2_pulse)
            btn_pic2.clicked.connect(lambda _, n="pic2", p=pic2_pulse: self._on_brew_button_clicked("PIC", n, p))
            pic2_layout.addWidget(btn_pic2)

        # --- pic1 라인 ---
        if pic1_layout is not None:
            # [stretch][pic1]
            pic1_layout.addStretch(1)

            pic1_pulse = getattr(self, "RAIL_TARGET_PULSE", {}).get("pic1")
            btn_pic1 = QPushButton("pic1")
            btn_pic1.setObjectName("btn_pic1")
            btn_pic1.setFixedHeight(40)
            if pic1_pulse is not None:
                btn_pic1.setToolTip(f"RAIL_PULSE: {pic1_pulse}")
            btn_pic1.setProperty("rail_pulse", pic1_pulse)
            btn_pic1.clicked.connect(lambda _, n="pic1", p=pic1_pulse: self._on_brew_button_clicked("PIC", n, p))
            pic1_layout.addWidget(btn_pic1)




if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = BrewDemoWindow()
    w.show()
    sys.exit(app.exec_())
