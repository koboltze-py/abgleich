"""
Mitarbeiter-Verwaltung: Übersicht, Umbenennen und Zusammenführen von Dubletten
(z. B. wenn ein Name in den Word-Dokumenten unterschiedlich geschrieben wurde).
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QInputDialog, QMessageBox,
    QHeaderView,
)
from PySide6.QtCore import Qt

from config import FIORI_TEXT
from gui.styles import table_style, button_primary, button_secondary
from functions.mitarbeiter_service import list_mitarbeiter, rename_mitarbeiter, merge_mitarbeiter


class MitarbeiterWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._aufbauen()
        self.aktualisieren()

    def _aufbauen(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        titel = QLabel("Mitarbeiter")
        titel.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {FIORI_TEXT};")
        layout.addWidget(titel)

        hinweis = QLabel(
            "Über 'Zusammenführen' können zwei Einträge, die denselben Mitarbeiter meinen "
            "(z. B. durch Schreibvarianten in den Word-Dokumenten), vereinigt werden."
        )
        hinweis.setWordWrap(True)
        layout.addWidget(hinweis)

        filter_zeile = QHBoxLayout()
        filter_zeile.addWidget(QLabel("Suche:"))
        self._such_feld = QLineEdit()
        self._such_feld.setPlaceholderText("Name filtern…")
        self._such_feld.setMaximumWidth(240)
        self._such_feld.textChanged.connect(self._anwenden_filter)
        filter_zeile.addWidget(self._such_feld)
        filter_zeile.addStretch()
        layout.addLayout(filter_zeile)

        self._tabelle = QTableWidget(0, 3)
        self._tabelle.setHorizontalHeaderLabels(["Mitarbeiter", "Anzahl Dienste", "Stunden gesamt"])
        self._tabelle.setStyleSheet(table_style())
        self._tabelle.setAlternatingRowColors(True)
        self._tabelle.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tabelle.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tabelle.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tabelle.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._tabelle, stretch=1)

        aktion_zeile = QHBoxLayout()
        btn_umbenennen = QPushButton("Umbenennen")
        btn_umbenennen.setStyleSheet(button_secondary())
        btn_umbenennen.clicked.connect(self._umbenennen)

        btn_zusammenfuehren = QPushButton("Zusammenführen (2 auswählen)")
        btn_zusammenfuehren.setStyleSheet(button_secondary())
        btn_zusammenfuehren.clicked.connect(self._zusammenfuehren)

        btn_aktualisieren = QPushButton("Aktualisieren")
        btn_aktualisieren.setStyleSheet(button_primary())
        btn_aktualisieren.clicked.connect(self.aktualisieren)

        aktion_zeile.addWidget(btn_umbenennen)
        aktion_zeile.addWidget(btn_zusammenfuehren)
        aktion_zeile.addStretch()
        aktion_zeile.addWidget(btn_aktualisieren)
        layout.addLayout(aktion_zeile)

    # ------------------------------------------------------------------
    def aktualisieren(self):
        self._alle_mitarbeiter = list_mitarbeiter()
        self._anwenden_filter()

    def _anwenden_filter(self):
        suchtext = self._such_feld.text().strip().lower()
        gefiltert = [
            m for m in self._alle_mitarbeiter
            if not suchtext or suchtext in m["name"].lower()
        ]
        self._tabelle.setRowCount(len(gefiltert))
        for zeile, m in enumerate(gefiltert):
            name_item = QTableWidgetItem(m["name"])
            name_item.setData(Qt.ItemDataRole.UserRole, m["id"])
            self._tabelle.setItem(zeile, 0, name_item)
            self._tabelle.setItem(zeile, 1, QTableWidgetItem(str(m["anzahl_dienste"])))
            stunden = round(m["summe_minuten"] / 60, 1)
            self._tabelle.setItem(zeile, 2, QTableWidgetItem(f"{stunden:.1f}"))

    def _ausgewaehlte_ids(self) -> list[tuple[int, str]]:
        zeilen = sorted({i.row() for i in self._tabelle.selectedIndexes()})
        ergebnis = []
        for zeile in zeilen:
            item = self._tabelle.item(zeile, 0)
            ergebnis.append((item.data(Qt.ItemDataRole.UserRole), item.text()))
        return ergebnis

    def _umbenennen(self):
        ausgewaehlt = self._ausgewaehlte_ids()
        if len(ausgewaehlt) != 1:
            QMessageBox.information(self, "Umbenennen", "Bitte genau einen Mitarbeiter auswählen.")
            return
        mitarbeiter_id, alter_name = ausgewaehlt[0]
        neuer_name, ok = QInputDialog.getText(self, "Mitarbeiter umbenennen", "Neuer Name:", text=alter_name)
        if ok and neuer_name.strip():
            try:
                rename_mitarbeiter(mitarbeiter_id, neuer_name.strip())
            except Exception as exc:
                QMessageBox.warning(self, "Fehler", str(exc))
                return
            self.aktualisieren()

    def _zusammenfuehren(self):
        ausgewaehlt = self._ausgewaehlte_ids()
        if len(ausgewaehlt) != 2:
            QMessageBox.information(
                self, "Zusammenführen", "Bitte genau zwei Mitarbeiter auswählen (Strg+Klick)."
            )
            return
        (id1, name1), (id2, name2) = ausgewaehlt
        antwort = QMessageBox.question(
            self, "Zusammenführen bestätigen",
            f"Alle Dienste von '{name2}' werden zu '{name1}' verschoben und "
            f"'{name2}' anschließend gelöscht.\nFortfahren?",
        )
        if antwort == QMessageBox.StandardButton.Yes:
            merge_mitarbeiter(id2, id1)
            self.aktualisieren()
