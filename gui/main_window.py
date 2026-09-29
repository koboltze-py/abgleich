"""
Hauptfenster mit Sidebar-Navigation im SAP-Fiori-Design (wie Nesk3).
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QStackedWidget, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from config import APP_NAME, APP_VERSION, FIORI_SIDEBAR_BG, FIORI_WHITE, QUELLE_STAERKEMELDUNG, QUELLE_URSPRUNGSPLANUNG
from gui.widgets import SidebarButton
from gui.dashboard import DashboardWidget
from gui.import_widget import ImportWidget
from gui.monatsuebersicht import MonatsuebersichtWidget
from gui.abgleich_widget import AbgleichWidget
from gui.mitarbeiter_widget import MitarbeiterWidget
from gui.einstellungen import EinstellungenWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1400, 860)

        zentral = QWidget()
        self.setCentralWidget(zentral)
        wurzel_layout = QHBoxLayout(zentral)
        wurzel_layout.setContentsMargins(0, 0, 0, 0)
        wurzel_layout.setSpacing(0)

        wurzel_layout.addWidget(self._sidebar_erstellen())

        self._stack = QStackedWidget()
        wurzel_layout.addWidget(self._stack, stretch=1)

        self._dashboard = DashboardWidget()
        self._import_ansicht = ImportWidget()
        self._monatsuebersicht_tagesdienst = MonatsuebersichtWidget(
            quelle_fest=QUELLE_STAERKEMELDUNG, titel="Monatsübersicht – Tagesdienstpläne"
        )
        self._monatsuebersicht_ursprung = MonatsuebersichtWidget(
            quelle_fest=QUELLE_URSPRUNGSPLANUNG, titel="Monatsübersicht – Ursprungsplanung"
        )
        self._abgleich = AbgleichWidget()
        self._mitarbeiter = MitarbeiterWidget()
        self._einstellungen = EinstellungenWidget()

        for widget in (
            self._dashboard, self._import_ansicht,
            self._monatsuebersicht_tagesdienst, self._monatsuebersicht_ursprung,
            self._abgleich, self._mitarbeiter, self._einstellungen,
        ):
            self._stack.addWidget(widget)

        # Nach einem Import werden Dashboard, Übersichten, Abgleich und Mitarbeiterliste aktualisiert
        self._import_ansicht.import_abgeschlossen.connect(self._dashboard.aktualisieren)
        self._import_ansicht.import_abgeschlossen.connect(self._monatsuebersicht_tagesdienst.aktualisieren)
        self._import_ansicht.import_abgeschlossen.connect(self._monatsuebersicht_ursprung.aktualisieren)
        self._import_ansicht.import_abgeschlossen.connect(self._abgleich.aktualisieren)
        self._import_ansicht.import_abgeschlossen.connect(self._mitarbeiter.aktualisieren)

        self._nav_buttons[0].setChecked(True)
        self._stack.setCurrentIndex(0)

    def _sidebar_erstellen(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setFixedWidth(230)
        sidebar.setStyleSheet(f"background: {FIORI_SIDEBAR_BG};")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        kopf = QWidget()
        kopf_layout = QVBoxLayout(kopf)
        kopf_layout.setContentsMargins(20, 26, 20, 20)
        titel = QLabel("NeSk Abgleich")
        titel.setStyleSheet(f"color: {FIORI_WHITE}; font-size: 18px; font-weight: bold;")
        untertitel = QLabel("DRK Flughafen Köln")
        untertitel.setStyleSheet("color: #a9bccb; font-size: 11px;")
        version = QLabel(f"v{APP_VERSION}")
        version.setStyleSheet("color: #7f95a7; font-size: 10px;")
        kopf_layout.addWidget(titel)
        kopf_layout.addWidget(untertitel)
        kopf_layout.addWidget(version)
        layout.addWidget(kopf)

        trenner = QFrame()
        trenner.setFixedHeight(1)
        trenner.setStyleSheet("background: rgba(255,255,255,0.12);")
        layout.addWidget(trenner)

        self._nav_buttons: list[SidebarButton] = []
        eintraege = [
            ("Dashboard", 0),
            ("Import", 1),
            ("Monatsübersicht Tagesdienste", 2),
            ("Monatsübersicht Ursprungsplan", 3),
            ("Abgleich", 4),
            ("Mitarbeiter", 5),
            ("Einstellungen", 6),
        ]
        for text, index in eintraege:
            btn = SidebarButton(text)
            btn.clicked.connect(lambda checked, i=index: self._seite_wechseln(i))
            layout.addWidget(btn)
            self._nav_buttons.append(btn)

        layout.addStretch()
        return sidebar

    def _seite_wechseln(self, index: int):
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)
        self._stack.setCurrentIndex(index)
        if index == 0:
            self._dashboard.aktualisieren()
        elif index == 2:
            self._monatsuebersicht_tagesdienst.aktualisieren()
        elif index == 3:
            self._monatsuebersicht_ursprung.aktualisieren()
        elif index == 4:
            self._abgleich.aktualisieren()
        elif index == 5:
            self._mitarbeiter.aktualisieren()
