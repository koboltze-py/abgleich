"""
Import-Ansicht: Tagesdienstpläne (Stärkemeldung-.docx) und Ursprungsplanung
(.xlsx) getrennt auswählen und einlesen, damit klar ist, was importiert wird.
"""
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QPlainTextEdit, QFileDialog, QFrame,
)
from PySide6.QtCore import Signal

from config import FIORI_TEXT, FIORI_BORDER, QUELLE_STAERKEMELDUNG, QUELLE_URSPRUNGSPLANUNG
from gui.styles import button_primary, button_secondary, card_style
from functions.import_service import importiere_dateien, ImportBericht


class _ImportSpalte(QFrame):
    """Eine Karte zur Auswahl und zum Import einer einzelnen Datenquelle
    (entweder Tagesdienstpläne/Word oder Ursprungsplanung/Excel)."""

    import_fertig = Signal(str, object)  # (Quelle, ImportBericht oder None)

    def __init__(self, titel: str, hinweis_text: str, endung: str, dialog_filter: str,
                 quelle: str, parent=None):
        super().__init__(parent)
        self._endung = endung
        self._quelle = quelle
        self._dialog_filter = dialog_filter
        self._dateipfade: list[str] = []

        self.setStyleSheet(card_style())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        titel_label = QLabel(titel)
        titel_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {FIORI_TEXT}; border: none;")
        layout.addWidget(titel_label)

        hinweis = QLabel(hinweis_text)
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet(f"color: {FIORI_TEXT}; border: none;")
        layout.addWidget(hinweis)

        button_zeile = QHBoxLayout()
        btn_ordner = QPushButton("Ordner wählen…")
        btn_ordner.setStyleSheet(button_secondary())
        btn_ordner.clicked.connect(self._ordner_waehlen)
        btn_dateien = QPushButton("Dateien wählen…")
        btn_dateien.setStyleSheet(button_secondary())
        btn_dateien.clicked.connect(self._dateien_waehlen)
        btn_leeren = QPushButton("Liste leeren")
        btn_leeren.setStyleSheet(button_secondary())
        btn_leeren.clicked.connect(self._liste_leeren)
        button_zeile.addWidget(btn_ordner)
        button_zeile.addWidget(btn_dateien)
        button_zeile.addWidget(btn_leeren)
        button_zeile.addStretch()
        layout.addLayout(button_zeile)

        self._liste = QListWidget()
        self._liste.setStyleSheet(f"border: 1px solid {FIORI_BORDER}; border-radius: 4px;")
        self._liste.setMinimumHeight(140)
        layout.addWidget(self._liste, stretch=1)

        self._anzahl_label = QLabel("Keine Dateien ausgewählt.")
        self._anzahl_label.setStyleSheet(f"color: {FIORI_TEXT}; border: none;")
        layout.addWidget(self._anzahl_label)

        self._btn_import = QPushButton(f"{titel} importieren")
        self._btn_import.setStyleSheet(button_primary())
        self._btn_import.clicked.connect(self._importieren)
        layout.addWidget(self._btn_import)

    # ------------------------------------------------------------------
    def _ordner_waehlen(self):
        ordner = QFileDialog.getExistingDirectory(self, f"Ordner mit {self._quelle} wählen")
        if not ordner:
            return
        gefunden = sorted(
            os.path.join(ordner, f) for f in os.listdir(ordner)
            if f.lower().endswith(self._endung) and not f.startswith("~$")
        )
        self._hinzufuegen(gefunden)

    def _dateien_waehlen(self):
        dateien, _ = QFileDialog.getOpenFileNames(self, f"{self._quelle}-Dateien wählen", "", self._dialog_filter)
        self._hinzufuegen(dateien)

    def _hinzufuegen(self, pfade: list[str]):
        for pfad in pfade:
            if pfad not in self._dateipfade:
                self._dateipfade.append(pfad)
                self._liste.addItem(QListWidgetItem(os.path.basename(pfad)))
        self._anzahl_label.setText(f"{len(self._dateipfade)} Datei(en) ausgewählt.")

    def _liste_leeren(self):
        self._dateipfade.clear()
        self._liste.clear()
        self._anzahl_label.setText("Keine Dateien ausgewählt.")

    def _importieren(self):
        if not self._dateipfade:
            self.import_fertig.emit(self._quelle, None)
            return
        self._btn_import.setEnabled(False)
        try:
            bericht = importiere_dateien(self._dateipfade)
        except Exception as exc:
            self._btn_import.setEnabled(True)
            fehler_bericht = ImportBericht(fehler=[str(exc)])
            self.import_fertig.emit(self._quelle, fehler_bericht)
            return
        self._btn_import.setEnabled(True)
        self.import_fertig.emit(self._quelle, bericht)


class ImportWidget(QWidget):
    """Ermöglicht das getrennte Einlesen von Tagesdienstplänen (Word) und
    Ursprungsplanung (Excel) in die Datenbank."""

    import_abgeschlossen = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._aufbauen()

    def _aufbauen(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        titel = QLabel("Import")
        titel.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {FIORI_TEXT};")
        layout.addWidget(titel)

        hinweis = QLabel(
            "Tagesdienstpläne (tatsächlich geleistete Dienste) und Ursprungsplanung (ursprünglicher "
            "Dienstplan) werden getrennt importiert, damit klar ist, welche Datenquelle eingelesen wird. "
            "Bereits importierte Dateien werden bei erneutem Import aktualisiert."
        )
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet(f"color: {FIORI_TEXT};")
        layout.addWidget(hinweis)

        spalten_zeile = QHBoxLayout()
        spalten_zeile.setSpacing(16)

        self._spalte_staerkemeldung = _ImportSpalte(
            titel="Tagesdienstpläne (Word)",
            hinweis_text="Stärkemeldung-Word-Dokumente (.docx) mit den tatsächlich geleisteten Diensten.",
            endung=".docx",
            dialog_filter="Word-Dokumente (*.docx)",
            quelle=QUELLE_STAERKEMELDUNG,
        )
        self._spalte_ursprungsplanung = _ImportSpalte(
            titel="Ursprungsplanung (Excel)",
            hinweis_text="Excel-Export des ursprünglichen Dienstplans (.xlsx), z. B. V2_MM.xlsx.",
            endung=".xlsx",
            dialog_filter="Excel-Dateien (*.xlsx)",
            quelle=QUELLE_URSPRUNGSPLANUNG,
        )
        for spalte in (self._spalte_staerkemeldung, self._spalte_ursprungsplanung):
            spalte.import_fertig.connect(self._import_fertig)
            spalten_zeile.addWidget(spalte, stretch=1)
        layout.addLayout(spalten_zeile, stretch=1)

        self._protokoll = QPlainTextEdit()
        self._protokoll.setReadOnly(True)
        self._protokoll.setPlaceholderText("Import-Protokoll erscheint hier…")
        self._protokoll.setStyleSheet(
            f"border: 1px solid {FIORI_BORDER}; border-radius: 4px; background: white;"
        )
        self._protokoll.setMinimumHeight(140)
        layout.addWidget(self._protokoll)

    # ------------------------------------------------------------------
    def _import_fertig(self, quelle: str, bericht):
        if bericht is None:
            self._protokoll.appendPlainText(f"⚠ {quelle}: bitte zuerst Dateien oder einen Ordner auswählen.")
            return

        if bericht.verarbeitete_dateien:
            self._protokoll.appendPlainText(
                f"✔ {quelle}: {bericht.verarbeitete_dateien} Datei(en) verarbeitet, "
                f"{bericht.importierte_eintraege} Dienst-Einträge, "
                f"{bericht.neue_mitarbeiter} neue Mitarbeiter."
            )
        for w in bericht.uebersprungen:
            self._protokoll.appendPlainText(f"⚠ {quelle}: {w}")
        for f in bericht.fehler:
            self._protokoll.appendPlainText(f"✘ {quelle}: {f}")

        self.import_abgeschlossen.emit()
