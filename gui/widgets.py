"""
Wiederverwendbare UI-Bausteine (KPI-Karte, Sidebar-Button).
"""
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QPushButton, QSizePolicy
from PySide6.QtCore import Qt

from config import FIORI_TEXT, FIORI_SIDEBAR_BG, FIORI_BLUE, FIORI_WHITE
from gui.styles import card_style


class KpiCard(QFrame):
    """Kleine Kennzahl-Karte für das Dashboard (Titel + große Zahl)."""

    def __init__(self, titel: str, wert: str = "-", akzent: str = FIORI_BLUE, parent=None):
        super().__init__(parent)
        self.setStyleSheet(card_style())
        self.setMinimumHeight(90)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        self._wert_label = QLabel(wert)
        self._wert_label.setStyleSheet(f"font-size: 26px; font-weight: bold; color: {akzent}; border: none;")

        titel_label = QLabel(titel)
        titel_label.setStyleSheet(f"font-size: 12px; color: {FIORI_TEXT}; border: none;")

        layout.addWidget(self._wert_label)
        layout.addWidget(titel_label)

    def set_wert(self, wert: str) -> None:
        self._wert_label.setText(wert)


class SidebarButton(QPushButton):
    """Navigations-Button für die Sidebar im Nesk3-Look."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(42)
        self.setStyleSheet(self._style(False))
        self.toggled.connect(lambda checked: self.setStyleSheet(self._style(checked)))

    @staticmethod
    def _style(checked: bool) -> str:
        if checked:
            return f"""
            QPushButton {{
                background: {FIORI_BLUE};
                color: {FIORI_WHITE};
                border: none;
                border-radius: 0px;
                text-align: left;
                padding-left: 20px;
                font-weight: bold;
                font-size: 13px;
            }}
            """
        return f"""
        QPushButton {{
            background: transparent;
            color: #d3dde5;
            border: none;
            text-align: left;
            padding-left: 20px;
            font-size: 13px;
        }}
        QPushButton:hover {{
            background: rgba(255, 255, 255, 0.08);
            color: {FIORI_WHITE};
        }}
        """
