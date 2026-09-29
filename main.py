"""
NeSk Abgleich – DRK Flughafen Köln
Einstiegspunkt der Anwendung.
"""
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from config import APP_NAME
from gui.styles import GLOBAL_QSS
from database.db import init_db
from gui.main_window import MainWindow


def main():
    init_db()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setFont(QFont("Segoe UI", 9))
    app.setStyleSheet(GLOBAL_QSS)

    fenster = MainWindow()
    fenster.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
