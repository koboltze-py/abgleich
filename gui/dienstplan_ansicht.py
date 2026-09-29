"""
Tagesdienstplan-Ansicht: reine Lese-Ansicht der Tagesdienstplan-Excel-Dateien
(wie in Nesk3), mit Ordner-Auswahl und Dateibaum. Im Gegensatz zu Nesk3 gibt
es hier bewusst KEINE Export- oder Bearbeitungsfunktionen - nur das Ansehen
eines Tagesdienstplans zur Unterstützung beim Abgleich.
"""
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTreeView,
    QSplitter, QFileSystemModel, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMessageBox, QFileDialog, QLineEdit,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from config import FIORI_TEXT, FIORI_BORDER, FIORI_BLUE
from gui.styles import button_secondary, card_style
from functions.dienstplan_parser import DienstplanParser
from functions.einstellungen_service import get_setting, set_setting

_EINSTELLUNG_ORDNER = "tagesdienstplan_ordner"

_TAG_DIENSTE   = frozenset({'T', 'T10', 'T8', 'DT', 'DT3'})
_NACHT_DIENSTE = frozenset({'N', 'N10', 'NF', 'DN', 'DN3'})
_STATIONSLEITUNG = {'lars peters'}

_FARBEN = {
    'Dispo':           QColor('#dce8f5'),
    'Betreuer':        QColor('#ffffff'),
    'Stationsleitung': QColor('#fff8e1'),
    'Krank':           QColor('#fce8e8'),
    'KrankDispo':      QColor('#f0d0d0'),
}
_TEXT_FARBEN = {
    'Dispo':           QColor('#0a5ba4'),
    'Betreuer':        QColor('#1a1a1a'),
    'Stationsleitung': QColor('#7a5000'),
    'Krank':           QColor('#bb0000'),
    'KrankDispo':      QColor('#7a0000'),
}


class DienstplanAnsichtWidget(QWidget):
    """Ordner mit Tagesdienstplan-Excel-Dateien durchsuchen und einen Tag
    zur Ansicht öffnen (reine Anzeige, kein Export, keine Bearbeitung)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fs_model: QFileSystemModel | None = None
        self._zeilen_namen: list[str | None] = []  # None = Abschnitts-Kopfzeile, sonst Personenname
        self._aufbauen()
        self._baum_aufbauen()

    # ------------------------------------------------------------------
    def _aufbauen(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        titel = QLabel("Tagesdienstpläne")
        titel.setStyleSheet(f"font-weight: bold; color: {FIORI_TEXT}; border: none;")
        layout.addWidget(titel)

        ordner_zeile = QHBoxLayout()
        btn_ordner = QPushButton("Ordner wählen…")
        btn_ordner.setStyleSheet(button_secondary())
        btn_ordner.clicked.connect(self._ordner_waehlen)
        ordner_zeile.addWidget(btn_ordner)
        ordner_zeile.addStretch()
        layout.addLayout(ordner_zeile)

        self._ordner_label = QLabel("Kein Ordner ausgewählt.")
        self._ordner_label.setWordWrap(True)
        self._ordner_label.setStyleSheet("color: #888; font-size: 10px; border: none;")
        layout.addWidget(self._ordner_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, stretch=1)

        # --- Dateibaum ---
        baum_rahmen = QWidget()
        baum_rahmen.setMinimumWidth(160)
        baum_rahmen.setMaximumWidth(260)
        baum_layout = QVBoxLayout(baum_rahmen)
        baum_layout.setContentsMargins(0, 0, 0, 0)

        self._baum = QTreeView()
        self._baum.setStyleSheet(f"""
            QTreeView {{ background-color: white; border: 1px solid {FIORI_BORDER}; border-radius: 4px; }}
            QTreeView::item {{ padding: 2px; }}
            QTreeView::item:selected {{ background-color: {FIORI_BLUE}; color: white; }}
        """)
        self._baum.setAnimated(True)
        self._baum.setSortingEnabled(True)
        self._baum.activated.connect(self._datei_aktiviert)
        baum_layout.addWidget(self._baum)
        splitter.addWidget(baum_rahmen)

        # --- Vorschau ---
        vorschau_rahmen = QWidget()
        vorschau_layout = QVBoxLayout(vorschau_rahmen)
        vorschau_layout.setContentsMargins(0, 0, 0, 0)
        vorschau_layout.setSpacing(4)

        self._datum_label = QLabel("")
        self._datum_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self._datum_label.setStyleSheet(f"color: {FIORI_TEXT}; border: none;")
        self._datum_label.setVisible(False)
        vorschau_layout.addWidget(self._datum_label)

        self._status_label = QLabel("Datei im Baum links doppelklicken, um sie zu laden.")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #888; border: none;")
        vorschau_layout.addWidget(self._status_label)

        self._suche_feld = QLineEdit()
        self._suche_feld.setPlaceholderText("Name suchen…")
        self._suche_feld.textChanged.connect(self._suche_geaendert)
        vorschau_layout.addWidget(self._suche_feld)

        self._tabelle = QTableWidget(0, 5)
        self._tabelle.setHorizontalHeaderLabels(["Kategorie", "Name", "Dienst", "Von", "Bis"])
        self._tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._tabelle.horizontalHeader().setStretchLastSection(False)
        self._tabelle.verticalHeader().setVisible(False)
        self._tabelle.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tabelle.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tabelle.setAlternatingRowColors(True)
        self._tabelle.setStyleSheet(f"border: 1px solid {FIORI_BORDER}; border-radius: 4px;")
        vorschau_layout.addWidget(self._tabelle, stretch=1)

        splitter.addWidget(vorschau_rahmen)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    # ------------------------------------------------------------------
    def _baum_aufbauen(self):
        ordner = get_setting(_EINSTELLUNG_ORDNER)
        if not ordner or not os.path.isdir(ordner):
            self._ordner_label.setText("Kein Ordner ausgewählt. Bitte oben einen Ordner wählen.")
            return

        self._fs_model = QFileSystemModel(self)
        self._fs_model.setNameFilters(["*.xlsx", "*.xls"])
        self._fs_model.setNameFilterDisables(False)
        root_idx = self._fs_model.setRootPath(ordner)

        self._baum.setModel(self._fs_model)
        self._baum.setRootIndex(root_idx)
        for spalte in range(1, 4):
            self._baum.hideColumn(spalte)
        self._baum.header().setVisible(False)

        self._ordner_label.setText(ordner)

    def _ordner_waehlen(self):
        start = get_setting(_EINSTELLUNG_ORDNER) or os.path.expanduser("~")
        ordner = QFileDialog.getExistingDirectory(self, "Ordner mit Tagesdienstplänen wählen", start)
        if not ordner:
            return
        set_setting(_EINSTELLUNG_ORDNER, ordner)
        if self._fs_model is not None:
            self._baum.setModel(None)
            self._fs_model.deleteLater()
            self._fs_model = None
        self._baum_aufbauen()

    # ------------------------------------------------------------------
    def _datei_aktiviert(self, index):
        if self._fs_model is None:
            return
        pfad = self._fs_model.filePath(index)
        if os.path.isfile(pfad) and pfad.lower().endswith((".xlsx", ".xls")):
            self._datei_laden(pfad)

    def _datei_laden(self, pfad: str):
        self._status_label.setText("Datei wird eingelesen …")
        self._status_label.setStyleSheet("color: #555; border: none;")
        self._status_label.repaint()

        ergebnis = DienstplanParser(pfad, alle_anzeigen=True).parse()
        if not ergebnis["success"]:
            QMessageBox.critical(
                self, "Fehler beim Einlesen",
                f"Die Datei konnte nicht gelesen werden:\n\n{ergebnis['error']}"
            )
            self._status_label.setText("Fehler beim Einlesen.")
            self._status_label.setStyleSheet("color: #bb0000; border: none;")
            return

        datum = ergebnis.get("datum")
        if datum:
            self._datum_label.setText(f"Datum: {datum}")
            self._datum_label.setVisible(True)
        else:
            self._datum_label.setVisible(False)

        self._tabelle_befuellen(ergebnis)
        self._status_label.setText(f"Geladen: {os.path.basename(pfad)}")
        self._status_label.setStyleSheet("color: #107e3e; border: none;")
        self._suche_feld.clear()

    # ------------------------------------------------------------------
    def _tabelle_befuellen(self, daten: dict):
        """Baut die Vorschau-Tabelle genau wie in Nesk3 auf (Abschnitte nach
        Tag-/Nachtdienst/Sonstige/Krank, farblich gruppiert nach Dispo/Betreuer)."""
        tag_personen, nacht_personen, sonst_personen = [], [], []
        for kat, liste in (("Dispo", daten.get("dispo", [])), ("Betreuer", daten.get("betreuer", []))):
            for p in liste:
                name_lower = p.get("vollname", "").strip().lower()
                effekt_kat = "Stationsleitung" if name_lower in _STATIONSLEITUNG else kat
                dk = (p.get("dienst_kategorie") or "").upper()
                if dk in _TAG_DIENSTE:
                    tag_personen.append((effekt_kat, p))
                elif dk in _NACHT_DIENSTE:
                    nacht_personen.append((effekt_kat, p))
                else:
                    sonst_personen.append((effekt_kat, p))

        krank_tag_dispo, krank_tag_betr = [], []
        krank_nacht_dispo, krank_nacht_betr = [], []
        krank_sonder = []
        for p in daten.get("kranke", []):
            stype = p.get("krank_schicht_typ") or "sonderdienst"
            ist_d = p.get("krank_ist_dispo", False)
            if stype == "tagdienst":
                (krank_tag_dispo if ist_d else krank_tag_betr).append(p)
            elif stype == "nachtdienst":
                (krank_nacht_dispo if ist_d else krank_nacht_betr).append(p)
            else:
                krank_sonder.append(p)

        krank_tag_personen = [("KrankDispo", p) for p in krank_tag_dispo] + [("Krank", p) for p in krank_tag_betr]
        krank_nacht_personen = [("KrankDispo", p) for p in krank_nacht_dispo] + [("Krank", p) for p in krank_nacht_betr]
        krank_sonder_personen = [("Krank", p) for p in krank_sonder]

        abschnitte = []
        if tag_personen:
            abschnitte.append(("Tagdienst", "#1565a8", "#ffffff", tag_personen))
        if nacht_personen:
            abschnitte.append(("Nachtdienst", "#0d2b4a", "#e8eeff", nacht_personen))
        if sonst_personen:
            abschnitte.append(("Sonstige", "#555555", "#ffffff", sonst_personen))
        if krank_tag_personen:
            abschnitte.append(("Krank – Tagdienst", "#8b0000", "#ffe8e8", krank_tag_personen))
        if krank_nacht_personen:
            abschnitte.append(("Krank – Nachtdienst", "#5a0000", "#f5d0d0", krank_nacht_personen))
        if krank_sonder_personen:
            abschnitte.append(("Krank – Sonderdienst", "#6b3300", "#fdebd0", krank_sonder_personen))

        total_rows = sum(1 + len(personen) for _, _, _, personen in abschnitte)
        self._tabelle.clearSpans()
        self._tabelle.setRowCount(total_rows)
        self._zeilen_namen = [None] * total_rows

        row = 0
        sep_font = QFont("Arial", 10, QFont.Weight.Bold)
        for label_text, hdr_bg, hdr_fg, personen in abschnitte:
            self._tabelle.setSpan(row, 0, 1, 5)
            sep_item = QTableWidgetItem(label_text)
            sep_item.setBackground(QColor(hdr_bg))
            sep_item.setForeground(QColor(hdr_fg))
            sep_item.setFont(sep_font)
            sep_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._tabelle.setItem(row, 0, sep_item)
            row += 1

            for kategorie, p in personen:
                bg = _FARBEN.get(kategorie, QColor("#ffffff"))
                fg = _TEXT_FARBEN.get(kategorie, QColor("#1a1a1a"))
                kat_anzeige = "Dispo" if kategorie == "KrankDispo" else ("Betreuer" if kategorie == "Krank" else kategorie)
                dienst_anzeige = (p.get("krank_abgeleiteter_dienst") or "") if p.get("ist_krank") else (p.get("dienst_kategorie") or "")

                vals = [kat_anzeige, p.get("anzeigename", ""), dienst_anzeige, p.get("start_zeit", "") or "", p.get("end_zeit", "") or ""]
                for col, wert in enumerate(vals):
                    item = QTableWidgetItem(wert)
                    item.setBackground(bg)
                    item.setForeground(fg)
                    self._tabelle.setItem(row, col, item)

                if p.get("ist_bulmorfahrer"):
                    for col in range(5):
                        self._tabelle.item(row, col).setBackground(QColor("#fff3b0"))
                self._zeilen_namen[row] = p.get("anzeigename", "")
                row += 1

        self._tabelle.resizeColumnsToContents()
        self._suche_geaendert(self._suche_feld.text())

    def _suche_geaendert(self, text: str):
        """Blendet Personen-Zeilen aus, deren Name nicht zum Suchtext passt;
        ein Abschnitt wird komplett ausgeblendet, wenn keine seiner Zeilen passt."""
        text = text.strip().lower()
        abschnitt_start = 0
        abschnitt_sichtbar = True
        for row, name in enumerate(self._zeilen_namen):
            if name is None:
                self._tabelle.setRowHidden(abschnitt_start, not abschnitt_sichtbar)
                abschnitt_start = row
                abschnitt_sichtbar = False
            else:
                sichtbar = not text or text in name.lower()
                self._tabelle.setRowHidden(row, not sichtbar)
                abschnitt_sichtbar = abschnitt_sichtbar or sichtbar
        if self._zeilen_namen:
            self._tabelle.setRowHidden(abschnitt_start, not abschnitt_sichtbar)

