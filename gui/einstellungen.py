"""
Einstellungen: Anzeige der Datenbank-Informationen sowie Zurücksetzen der Daten.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QMessageBox, QHBoxLayout

from config import FIORI_TEXT, DB_PATH, APP_NAME, APP_VERSION
from gui.styles import button_danger
from database.db import get_connection


class EinstellungenWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._aufbauen()

    def _aufbauen(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        titel = QLabel("Einstellungen")
        titel.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {FIORI_TEXT};")
        layout.addWidget(titel)

        info = QLabel(
            f"Anwendung: {APP_NAME}\n"
            f"Version: {APP_VERSION}\n"
            f"Datenbankdatei: {DB_PATH}"
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {FIORI_TEXT};")
        layout.addWidget(info)

        layout.addSpacing(20)
        gefahr_titel = QLabel("Alle importierten Daten löschen")
        gefahr_titel.setStyleSheet(f"font-weight: bold; color: {FIORI_TEXT};")
        layout.addWidget(gefahr_titel)

        gefahr_hinweis = QLabel(
            "Entfernt alle Mitarbeiter, Dokumente und Dienst-Einträge unwiderruflich aus der Datenbank."
        )
        gefahr_hinweis.setWordWrap(True)
        layout.addWidget(gefahr_hinweis)

        zeile = QHBoxLayout()
        btn_reset = QPushButton("Datenbank zurücksetzen")
        btn_reset.setStyleSheet(button_danger())
        btn_reset.clicked.connect(self._zuruecksetzen)
        zeile.addWidget(btn_reset)
        zeile.addStretch()
        layout.addLayout(zeile)

        layout.addStretch()

    def _zuruecksetzen(self):
        antwort = QMessageBox.question(
            self, "Datenbank zurücksetzen",
            "Wirklich ALLE importierten Daten unwiderruflich löschen?",
        )
        if antwort != QMessageBox.StandardButton.Yes:
            return
        con = get_connection()
        try:
            con.execute("DELETE FROM dienste")
            con.execute("DELETE FROM dokumente")
            con.execute("DELETE FROM mitarbeiter")
            con.commit()
        finally:
            con.close()
        QMessageBox.information(self, "Erledigt", "Alle Daten wurden gelöscht.")
