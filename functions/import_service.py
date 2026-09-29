"""
Import-Service: liest Stärkemeldung-.docx- und Ursprungsplanung-.xlsx-Dateien
ein und schreibt die Ergebnisse in die SQLite-Datenbank (Mitarbeiter,
Dokumente, Dienste).
"""
import os
from dataclasses import dataclass, field

from config import QUELLE_STAERKEMELDUNG, QUELLE_URSPRUNGSPLANUNG
from database.db import get_connection, jetzt
from functions.staerkemeldung_parser import parse_datei as parse_staerkemeldung
from functions.ursprungsplanung_parser import parse_datei as parse_ursprungsplanung

_PARSER_NACH_ENDUNG = {
    ".docx": (parse_staerkemeldung, QUELLE_STAERKEMELDUNG),
    ".xlsx": (parse_ursprungsplanung, QUELLE_URSPRUNGSPLANUNG),
}


@dataclass
class ImportBericht:
    verarbeitete_dateien: int = 0
    importierte_eintraege: int = 0
    neue_mitarbeiter: int = 0
    uebersprungen: list[str] = field(default_factory=list)
    fehler: list[str] = field(default_factory=list)


def _mitarbeiter_id(con, name: str, bericht: ImportBericht) -> int:
    row = con.execute("SELECT id FROM mitarbeiter WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
    if row:
        return row["id"]
    cur = con.execute(
        "INSERT INTO mitarbeiter (name, aktiv, erstellt_am) VALUES (?, 1, ?)",
        (name, jetzt()),
    )
    bericht.neue_mitarbeiter += 1
    return cur.lastrowid


def importiere_dateien(dateipfade: list[str]) -> ImportBericht:
    """Importiert eine Liste von .docx- (Stärkemeldung) und/oder .xlsx-Dateipfaden
    (Ursprungsplanung). Bereits vorhandene Dokumente (gleicher Pfad) werden
    aktualisiert: alte Dienst-Einträge werden ersetzt."""
    bericht = ImportBericht()
    con = get_connection()
    try:
        for pfad in dateipfade:
            endung = os.path.splitext(pfad)[1].lower()
            if endung not in _PARSER_NACH_ENDUNG or os.path.basename(pfad).startswith("~$"):
                continue
            parse_datei, quelle = _PARSER_NACH_ENDUNG[endung]
            ergebnis = parse_datei(pfad)
            bericht.verarbeitete_dateien += 1

            if ergebnis.fehler:
                bericht.fehler.append(f"{os.path.basename(pfad)}: {ergebnis.fehler}")
                continue
            if not ergebnis.eintraege:
                bericht.uebersprungen.append(f"{os.path.basename(pfad)}: keine Dienst-Einträge gefunden")
                continue

            bestehend = con.execute(
                "SELECT id FROM dokumente WHERE dateipfad = ?", (pfad,)
            ).fetchone()
            if bestehend:
                dok_id = bestehend["id"]
                con.execute("DELETE FROM dienste WHERE dokument_id = ?", (dok_id,))
                con.execute(
                    "UPDATE dokumente SET quelle=?, von_datum=?, bis_datum=?, importiert_am=?, anzahl_eintraege=? WHERE id=?",
                    (
                        quelle,
                        ergebnis.von_datum.isoformat(),
                        ergebnis.bis_datum.isoformat() if ergebnis.bis_datum else None,
                        jetzt(), len(ergebnis.eintraege), dok_id,
                    ),
                )
            else:
                cur = con.execute(
                    "INSERT INTO dokumente (dateipfad, dateiname, quelle, von_datum, bis_datum, importiert_am, anzahl_eintraege) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        pfad, os.path.basename(pfad), quelle,
                        ergebnis.von_datum.isoformat(),
                        ergebnis.bis_datum.isoformat() if ergebnis.bis_datum else None,
                        jetzt(), len(ergebnis.eintraege),
                    ),
                )
                dok_id = cur.lastrowid

            for eintrag in ergebnis.eintraege:
                ma_id = _mitarbeiter_id(con, eintrag.name, bericht)
                con.execute(
                    "INSERT INTO dienste (mitarbeiter_id, dokument_id, quelle, kategorie, ebene, datum, start_zeit, end_zeit, end_datum, dauer_minuten) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        ma_id, dok_id, quelle, eintrag.kategorie, eintrag.ebene, eintrag.datum.isoformat(),
                        eintrag.start_zeit, eintrag.end_zeit, eintrag.end_datum.isoformat(),
                        eintrag.dauer_minuten,
                    ),
                )
                bericht.importierte_eintraege += 1

        con.commit()
    finally:
        con.close()
    return bericht

