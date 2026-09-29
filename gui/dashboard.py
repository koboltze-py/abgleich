"""
Dashboard: Kennzahlen-Übersicht (Anzahl Mitarbeiter, Dienste, Dokumente, letzter Import).
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt

from config import FIORI_TEXT, FIORI_BLUE, FIORI_SUCCESS, FIORI_WARNING
from gui.widgets import KpiCard
from functions.dienste_service import get_dashboard_stats


class DashboardWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._aufbauen()
        self.aktualisieren()

    def _aufbauen(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        titel = QLabel("Dashboard")
        titel.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {FIORI_TEXT};")
        layout.addWidget(titel)

        untertitel = QLabel("Abgleich der Stärkemeldungen – Mitarbeiter und Dienstzeiten")
        untertitel.setStyleSheet(f"color: {FIORI_TEXT};")
        layout.addWidget(untertitel)

        karten_zeile = QHBoxLayout()
        karten_zeile.setSpacing(14)
        self._karte_mitarbeiter = KpiCard("Mitarbeiter", akzent=FIORI_BLUE)
        self._karte_dienste = KpiCard("Dienst-Einträge", akzent=FIORI_SUCCESS)
        self._karte_dokumente = KpiCard("Importierte Dokumente", akzent=FIORI_WARNING)
        karten_zeile.addWidget(self._karte_mitarbeiter)
        karten_zeile.addWidget(self._karte_dienste)
        karten_zeile.addWidget(self._karte_dokumente)
        layout.addLayout(karten_zeile)

        self._info_label = QLabel()
        self._info_label.setStyleSheet(f"color: {FIORI_TEXT};")
        layout.addWidget(self._info_label)

        layout.addStretch()

    def aktualisieren(self):
        stats = get_dashboard_stats()
        self._karte_mitarbeiter.set_wert(str(stats["anzahl_mitarbeiter"]))
        self._karte_dienste.set_wert(str(stats["anzahl_dienste"]))
        self._karte_dokumente.set_wert(str(stats["anzahl_dokumente"]))

        letzter_import = stats["letzter_import"] or "noch kein Import"
        letzter_tag = stats["letzter_tag"] or "-"
        self._info_label.setText(
            f"Letzter Import: {letzter_import}\nAktuellster erfasster Diensttag: {letzter_tag}"
        )
