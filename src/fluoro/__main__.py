"""Start the fluoro window: `fluoro` or `fluoro <folder>`."""
import sys

from PySide6.QtWidgets import QApplication

from .app import MainWindow


USAGE = """usage: fluoro [folder]

Opens the fluoro window. Optionally opens a folder of image pairs (<name>_WL + <name>_FL) directly."""


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(USAGE)
        return 0
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.resize(1400, 850)
    win.show()
    if len(sys.argv) > 1:
        win.open_folder(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
