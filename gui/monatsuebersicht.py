"""
Monatsübersicht: Kalenderartige Pivot-Ansicht (Mitarbeiter x Tage) und eine
filter- und sortierbare Liste aller Dienst-Einträge eines Monats.
"""
import calendar
from datetime import date

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit,
    QTableWidget, QTableWidgetItem, QTabWidget, QTableView, QHeaderView,
    QAbstractItemView,
)
from PySide6.QtCore import Qt, QSortFilterProxyModel, QModelIndex
from PySide6.QtGui import QStandardItemModel, QStandardItem, QColor

from config import FIORI_TEXT, KATEGORIE_FARBEN, KATEGORIE_FARBE_STANDARD
from gui.styles import table_style
from functions.dienste_service import (
    get_dienste_fuer_monat, get_verfuegbare_monate, get_kategorien, get_quellen,
)

MONATSNAMEN = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]
WOCHENTAGE_KURZ = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
QUELLE_KUERZEL = {"Stärkemeldung": "SM", "Ursprungsplanung": "UP"}


def _hex_zu_rgba(hex_farbe: str, alpha: int) -> QColor:
    c = QColor(hex_farbe)
    c.setAlpha(alpha)
    return c


class _MehrfachFilterProxy(QSortFilterProxyModel):
    """Kombiniert Text-, Kategorie- und Tagesbereich-Filter logisch (UND-Verknüpfung)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._suchtext = ""
        self._kategorie = "Alle"
        self._quelle = "Alle"
        self._tag_von = 1
        self._tag_bis = 31

    def set_suchtext(self, text: str):
        self._suchtext = text.strip().lower()
        self.invalidateFilter()

    def set_kategorie(self, kategorie: str):
        self._kategorie = kategorie
        self.invalidateFilter()

    def set_quelle(self, quelle: str):
        self._quelle = quelle
        self.invalidateFilter()

    def set_tagesbereich(self, von: int, bis: int):
        self._tag_von, self._tag_bis = von, bis
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        mitarbeiter = model.index(source_row, 2).data() or ""
        quelle = model.index(source_row, 3).data() or ""
        kategorie = model.index(source_row, 4).data() or ""
        tag = model.index(source_row, 6).data()  # versteckte Spalte: Tag als int

        if self._suchtext and self._suchtext not in mitarbeiter.lower():
            return False
        if self._kategorie != "Alle" and kategorie != self._kategorie:
            return False
        if self._quelle != "Alle" and quelle != self._quelle:
            return False
        if tag is not None and not (self._tag_von <= int(tag) <= self._tag_bis):
            return False
        return True


class MonatsuebersichtWidget(QWidget):
    def __init__(self, parent=None, quelle_fest: str | None = None, titel: str = "Monatsübersicht"):
        super().__init__(parent)
        self._daten: list[dict] = []
        self._jahr: int | None = None
        self._monat: int | None = None
        self._anzahl_tage: int = 31
        self._quelle_fest = quelle_fest
        self._titel = titel
        self._aufbauen()
        self.aktualisieren()

    # ------------------------------------------------------------------
    def _aufbauen(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        titel = QLabel(self._titel)
        titel.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {FIORI_TEXT};")
        layout.addWidget(titel)

        filter_zeile = QHBoxLayout()
        filter_zeile.addWidget(QLabel("Monat:"))
        self._monat_combo = QComboBox()
        self._monat_combo.currentIndexChanged.connect(self._monat_gewechselt)
        filter_zeile.addWidget(self._monat_combo)

        filter_zeile.addSpacing(20)
        filter_zeile.addWidget(QLabel("Mitarbeiter:"))
        self._such_feld = QLineEdit()
        self._such_feld.setPlaceholderText("Name filtern…")
        self._such_feld.setMaximumWidth(200)
        self._such_feld.textChanged.connect(self._filter_geaendert)
        filter_zeile.addWidget(self._such_feld)

        filter_zeile.addSpacing(20)
        filter_zeile.addWidget(QLabel("Kategorie:"))
        self._kategorie_combo = QComboBox()
        self._kategorie_combo.addItem("Alle")
        self._kategorie_combo.currentTextChanged.connect(self._filter_geaendert)
        filter_zeile.addWidget(self._kategorie_combo)

        filter_zeile.addSpacing(20)
        self._quelle_label = QLabel("Quelle:")
        filter_zeile.addWidget(self._quelle_label)
        self._quelle_combo = QComboBox()
        self._quelle_combo.addItem("Alle")
        self._quelle_combo.currentTextChanged.connect(self._filter_geaendert)
        filter_zeile.addWidget(self._quelle_combo)
        if self._quelle_fest:
            self._quelle_label.setVisible(False)
            self._quelle_combo.setVisible(False)

        filter_zeile.addSpacing(20)
        filter_zeile.addWidget(QLabel("Tag von:"))
        self._tag_von_combo = QComboBox()
        self._tag_von_combo.currentIndexChanged.connect(self._filter_geaendert)
        filter_zeile.addWidget(self._tag_von_combo)
        filter_zeile.addWidget(QLabel("bis:"))
        self._tag_bis_combo = QComboBox()
        self._tag_bis_combo.currentIndexChanged.connect(self._filter_geaendert)
        filter_zeile.addWidget(self._tag_bis_combo)

        filter_zeile.addStretch()
        layout.addLayout(filter_zeile)

        self._reiter = QTabWidget()
        layout.addWidget(self._reiter, stretch=1)

        # --- Tab 1: Kalenderansicht (Pivot) ---
        self._pivot_tabelle = QTableWidget()
        self._pivot_tabelle.setStyleSheet(table_style())
        self._pivot_tabelle.setAlternatingRowColors(True)
        self._pivot_tabelle.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._pivot_tabelle.verticalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        self._reiter.addTab(self._pivot_tabelle, "Kalenderansicht")

        # --- Tab 2: Dienste-Liste (filter- und sortierbar) ---
        self._listen_modell = QStandardItemModel(self)
        self._listen_modell.setHorizontalHeaderLabels(
            ["Datum", "Wochentag", "Mitarbeiter", "Quelle", "Kategorie", "Zeit", "Tag", "Dauer (Std)"]
        )
        self._proxy = _MehrfachFilterProxy(self)
        self._proxy.setSourceModel(self._listen_modell)
        self._proxy.setSortRole(Qt.ItemDataRole.UserRole)

        self._listen_ansicht = QTableView()
        self._listen_ansicht.setModel(self._proxy)
        self._listen_ansicht.setStyleSheet(table_style())
        self._listen_ansicht.setAlternatingRowColors(True)
        self._listen_ansicht.setSortingEnabled(True)
        self._listen_ansicht.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._listen_ansicht.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._listen_ansicht.horizontalHeader().setStretchLastSection(True)
        self._listen_ansicht.setColumnHidden(6, True)  # "Tag" nur intern für Filter
        if self._quelle_fest:
            self._listen_ansicht.setColumnHidden(3, True)  # "Quelle" bei fester Quelle nicht nötig
        self._reiter.addTab(self._listen_ansicht, "Dienste-Liste")

    # ------------------------------------------------------------------
    def _monate_laden(self):
        self._monat_combo.blockSignals(True)
        self._monat_combo.clear()
        monate = get_verfuegbare_monate(self._quelle_fest)
        heute = date.today()
        if not monate:
            monate = [(heute.year, heute.month)]
        for jahr, monat in monate:
            self._monat_combo.addItem(f"{MONATSNAMEN[monat - 1]} {jahr}", (jahr, monat))
        self._monat_combo.blockSignals(False)

    def _monat_gewechselt(self):
        self._daten_laden()

    def _filter_geaendert(self):
        self._proxy.set_suchtext(self._such_feld.text())
        self._proxy.set_kategorie(self._kategorie_combo.currentText())
        self._proxy.set_quelle(self._quelle_combo.currentText())
        von = self._tag_von_combo.currentData()
        bis = self._tag_bis_combo.currentData()
        if von and bis:
            self._proxy.set_tagesbereich(von, bis)
        self._pivot_neu_zeichnen()

    def _gefilterte_daten(self) -> list[dict]:
        """Wendet dieselben Filter (Name/Kategorie/Quelle/Tagesbereich) wie die
        Dienste-Liste auch auf die Daten der Kalenderansicht (Pivot) an."""
        suchtext = self._such_feld.text().strip().lower()
        kategorie = self._kategorie_combo.currentText()
        quelle = self._quelle_combo.currentText()
        tag_von = self._tag_von_combo.currentData() or 1
        tag_bis = self._tag_bis_combo.currentData() or 31

        ergebnis = []
        for eintrag in self._daten:
            if suchtext and suchtext not in eintrag["mitarbeiter"].lower():
                continue
            if kategorie != "Alle" and eintrag["kategorie"] != kategorie:
                continue
            if quelle != "Alle" and eintrag["quelle"] != quelle:
                continue
            tag = int(eintrag["datum"].split("-")[2])
            if not (tag_von <= tag <= tag_bis):
                continue
            ergebnis.append(eintrag)
        return ergebnis

    def _pivot_neu_zeichnen(self):
        if self._jahr is None:
            return
        self._pivot_befuellen(self._jahr, self._monat, self._anzahl_tage, self._gefilterte_daten())

    # ------------------------------------------------------------------
    def aktualisieren(self):
        """Lädt verfügbare Monate/Kategorien neu und aktualisiert die Ansicht (z. B. nach Import)."""
        aktuelle_auswahl = self._monat_combo.currentData()
        self._monate_laden()
        if aktuelle_auswahl:
            idx = self._monat_combo.findData(aktuelle_auswahl)
            if idx >= 0:
                self._monat_combo.setCurrentIndex(idx)

        self._kategorie_combo.blockSignals(True)
        akt_kat = self._kategorie_combo.currentText()
        self._kategorie_combo.clear()
        self._kategorie_combo.addItem("Alle")
        self._kategorie_combo.addItems(get_kategorien(self._quelle_fest))
        idx = self._kategorie_combo.findText(akt_kat)
        self._kategorie_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._kategorie_combo.blockSignals(False)

        self._quelle_combo.blockSignals(True)
        akt_quelle = self._quelle_combo.currentText()
        self._quelle_combo.clear()
        self._quelle_combo.addItem("Alle")
        self._quelle_combo.addItems(get_quellen())
        idx = self._quelle_combo.findText(akt_quelle)
        self._quelle_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._quelle_combo.blockSignals(False)

        self._daten_laden()

    def _daten_laden(self):
        auswahl = self._monat_combo.currentData()
        if not auswahl:
            return
        jahr, monat = auswahl
        self._daten = get_dienste_fuer_monat(jahr, monat, self._quelle_fest)

        anzahl_tage = calendar.monthrange(jahr, monat)[1]
        self._jahr, self._monat, self._anzahl_tage = jahr, monat, anzahl_tage
        self._tag_von_combo.blockSignals(True)
        self._tag_bis_combo.blockSignals(True)
        self._tag_von_combo.clear()
        self._tag_bis_combo.clear()
        for tag in range(1, anzahl_tage + 1):
            self._tag_von_combo.addItem(str(tag), tag)
            self._tag_bis_combo.addItem(str(tag), tag)
        self._tag_bis_combo.setCurrentIndex(anzahl_tage - 1)
        self._tag_von_combo.blockSignals(False)
        self._tag_bis_combo.blockSignals(False)

        self._liste_befuellen(jahr, monat)
        self._filter_geaendert()

    # ------------------------------------------------------------------
    def _pivot_befuellen(self, jahr: int, monat: int, anzahl_tage: int, daten: list[dict]):
        mitarbeiter_namen = sorted({d["mitarbeiter"] for d in daten}, key=str.lower)

        tabelle = self._pivot_tabelle
        tabelle.clear()
        tabelle.setRowCount(len(mitarbeiter_namen))
        tabelle.setColumnCount(anzahl_tage)
        tabelle.setVerticalHeaderLabels(mitarbeiter_namen)

        header_labels = []
        for tag in range(1, anzahl_tage + 1):
            wochentag = WOCHENTAGE_KURZ[date(jahr, monat, tag).weekday()]
            header_labels.append(f"{tag:02d}\n{wochentag}")
        tabelle.setHorizontalHeaderLabels(header_labels)

        zeilen_index = {name: i for i, name in enumerate(mitarbeiter_namen)}
        zellen_texte: dict[tuple[int, int], list[str]] = {}
        zellen_kategorie: dict[tuple[int, int], str] = {}
        mehrere_quellen = len({d["quelle"] for d in daten}) > 1

        for eintrag in daten:
            zeile = zeilen_index[eintrag["mitarbeiter"]]
            tag = int(eintrag["datum"].split("-")[2])
            spalte = tag - 1
            text = f"{eintrag['start_zeit']}-{eintrag['end_zeit']}"
            if eintrag["kategorie"] and eintrag["kategorie"] != "Sonstige":
                text = f"{text} ({eintrag['kategorie'][:4]}.)"
            if mehrere_quellen:
                text = f"{text} [{QUELLE_KUERZEL.get(eintrag['quelle'], eintrag['quelle'][:2])}]"
            key = (zeile, spalte)
            zellen_texte.setdefault(key, []).append(text)
            zellen_kategorie.setdefault(key, eintrag["kategorie"])

        for (zeile, spalte), texte in zellen_texte.items():
            item = QTableWidgetItem("\n".join(texte))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            farbe_hex = KATEGORIE_FARBEN.get(zellen_kategorie[(zeile, spalte)], KATEGORIE_FARBE_STANDARD)
            item.setBackground(_hex_zu_rgba(farbe_hex, 35))
            tabelle.setItem(zeile, spalte, item)

        tabelle.resizeColumnsToContents()
        tabelle.horizontalHeader().setMinimumSectionSize(58)

    def _liste_befuellen(self, jahr: int, monat: int):
        self._listen_modell.removeRows(0, self._listen_modell.rowCount())
        for eintrag in self._daten:
            tag = int(eintrag["datum"].split("-")[2])
            wochentag = WOCHENTAGE_KURZ[date.fromisoformat(eintrag["datum"]).weekday()]
            zeit = f"{eintrag['start_zeit']} – {eintrag['end_zeit']}"
            if eintrag["end_datum"] != eintrag["datum"]:
                zeit += " (+1 Tag)"
            dauer_std = round(eintrag["dauer_minuten"] / 60, 2)

            datum_item = QStandardItem(eintrag["datum"])
            datum_item.setData(eintrag["datum"], Qt.ItemDataRole.UserRole)
            zeile = [
                datum_item,
                QStandardItem(wochentag),
                QStandardItem(eintrag["mitarbeiter"]),
                QStandardItem(eintrag["quelle"]),
                QStandardItem(eintrag["kategorie"]),
                QStandardItem(zeit),
                QStandardItem(str(tag)),
                QStandardItem(f"{dauer_std:.2f}"),
            ]
            for it in zeile:
                it.setEditable(False)
            self._listen_modell.appendRow(zeile)
