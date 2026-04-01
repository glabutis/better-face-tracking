#!/usr/bin/env python3
"""
Better Face Tracking — Canon PTZ Controller
Entry point.

Requirements:
  pip install -r requirements.txt
"""

import logging
import sys

from PyQt6.QtWidgets import QApplication

from src.ui.main_window import MainWindow


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Better Face Tracking")
    app.setApplicationDisplayName("Better Face Tracking")
    app.setOrganizationName("BFT")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
