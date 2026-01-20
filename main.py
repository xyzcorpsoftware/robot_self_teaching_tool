import sys
from PyQt5.QtWidgets import QApplication


# import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
    
from ui.connect_dialog import ConnectDialog


def main():
    app = QApplication(sys.argv)

    # 기본은 Fake로 개발 (필요하면 True로 바꿔서 Real 연결)
    dlg = ConnectDialog(use_real_robot=False)
    dlg.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
