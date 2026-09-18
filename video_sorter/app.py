from __future__ import annotations

import sys
from pathlib import Path
from typing import List

from PySide6.QtWidgets import QApplication

from . import config
from .ui.main_window import MainWindow


def main(argv: List[str] = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationDisplayName(config.APP_NAME)
    app.setOrganizationName(config.ORG_NAME)

    window = MainWindow()
    window.show()

    initial = [Path(arg) for arg in argv[1:] if Path(arg).exists()]
    if initial:
        window.open_paths(initial)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
