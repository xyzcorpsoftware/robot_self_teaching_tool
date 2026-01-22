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

    dlg = ConnectDialog()
    dlg.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
