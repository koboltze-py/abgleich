"""
Wiederverwendbare UI-Bausteine (KPI-Karte, Sidebar-Button, Zeitbereich-Editor).
"""
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QWidget, QTimeEdit, QCheckBox,
)
from PySide6.QtCore import Qt, QTime

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


class ZeitBereichEditor(QWidget):
    """Zeitbereich-Editor (Start-/Ende-Uhrzeit) für Tabellenzellen, z. B. die
    "Tatsächlich"-Spalte im Abgleich: verhindert per QTimeEdit ungültige
    Eingaben. Die Checkbox schaltet zwischen "keine Zeit hinterlegt" und
    einem aktiven Zeitbereich um."""

    def __init__(self, start: str | None, ende: str | None, on_change, parent=None):
        super().__init__(parent)
        self._on_change = on_change
        self._aktiv = start is not None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        self._checkbox = QCheckBox()
        self._checkbox.setToolTip("Zeit eintragen bzw. entfernen")
        self._checkbox.setChecked(self._aktiv)
        self._checkbox.toggled.connect(self._umgeschaltet)
        layout.addWidget(self._checkbox)

        self._start = QTimeEdit()
        self._start.setDisplayFormat("HH:mm")
        self._start.setTime(QTime.fromString(start, "HH:mm") if start else QTime(0, 0))
        self._start.setEnabled(self._aktiv)
        self._start.editingFinished.connect(self._geaendert)
        layout.addWidget(self._start)

        layout.addWidget(QLabel("–"))

        self._ende = QTimeEdit()
        self._ende.setDisplayFormat("HH:mm")
        self._ende.setTime(QTime.fromString(ende, "HH:mm") if ende else QTime(0, 0))
        self._ende.setEnabled(self._aktiv)
        self._ende.editingFinished.connect(self._geaendert)
        layout.addWidget(self._ende)

    def _umgeschaltet(self, aktiv: bool):
        self._aktiv = aktiv
        self._start.setEnabled(aktiv)
        self._ende.setEnabled(aktiv)
        self._geaendert()

    def _geaendert(self):
        if self._aktiv:
            self._on_change((self._start.time().toString("HH:mm"), self._ende.time().toString("HH:mm")))
        else:
            self._on_change(None)
