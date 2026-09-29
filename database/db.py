"""
SQLite-Datenbankzugriff für NeSk Abgleich.
Legt Schema an und stellt einfache Verbindungs-Hilfsfunktion bereit.
"""
import sqlite3
from datetime import datetime

from config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mitarbeiter (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    aktiv       INTEGER NOT NULL DEFAULT 1,
    erstellt_am TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dokumente (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    dateipfad        TEXT NOT NULL UNIQUE,
    dateiname        TEXT NOT NULL,
    quelle           TEXT NOT NULL DEFAULT 'Stärkemeldung',
    von_datum        TEXT,
    bis_datum        TEXT,
    importiert_am    TEXT NOT NULL,
    anzahl_eintraege INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dienste (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mitarbeiter_id  INTEGER NOT NULL REFERENCES mitarbeiter(id) ON DELETE CASCADE,
    dokument_id     INTEGER NOT NULL REFERENCES dokumente(id)   ON DELETE CASCADE,
    quelle          TEXT NOT NULL DEFAULT 'Stärkemeldung',
    kategorie       TEXT NOT NULL,
    ebene           TEXT,
    datum           TEXT NOT NULL,
    start_zeit      TEXT NOT NULL,
    end_zeit        TEXT NOT NULL,
    end_datum       TEXT NOT NULL,
    dauer_minuten   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dienste_datum          ON dienste(datum);
CREATE INDEX IF NOT EXISTS idx_dienste_mitarbeiter_id ON dienste(mitarbeiter_id);
CREATE INDEX IF NOT EXISTS idx_dienste_dokument_id    ON dienste(dokument_id);

-- Abgleich-Workflow: Bearbeitungsstatus je Mitarbeiter/Tag/Art einer Abweichung
-- zwischen Ursprungsplanung und Tagesdienstplänen (überlebt Reimporte, da nicht
-- an dienste.id, sondern an mitarbeiter_id+datum+art gebunden).
CREATE TABLE IF NOT EXISTS abgleich_status (
    mitarbeiter_id INTEGER NOT NULL REFERENCES mitarbeiter(id) ON DELETE CASCADE,
    datum          TEXT NOT NULL,
    art            TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'offen',
    bearbeitet_am  TEXT,
    PRIMARY KEY (mitarbeiter_id, datum, art)
);

-- Merkt sich je Monat, bei welchem Mitarbeiter der Abgleich zuletzt bearbeitet wurde.
CREATE TABLE IF NOT EXISTS abgleich_fortschritt (
    jahr            INTEGER NOT NULL,
    monat           INTEGER NOT NULL,
    mitarbeiter_id  INTEGER REFERENCES mitarbeiter(id) ON DELETE SET NULL,
    aktualisiert_am TEXT NOT NULL,
    PRIMARY KEY (jahr, monat)
);
"""

# Spalten, die nachträglich zu bestehenden Datenbanken hinzugefügt wurden
# (Migration für vor der Einführung von "Ursprungsplanung"-Importen angelegte DBs).
_MIGRATIONEN = {
    "dokumente": ["ALTER TABLE dokumente ADD COLUMN quelle TEXT NOT NULL DEFAULT 'Stärkemeldung'"],
    "dienste": [
        "ALTER TABLE dienste ADD COLUMN quelle TEXT NOT NULL DEFAULT 'Stärkemeldung'",
        "ALTER TABLE dienste ADD COLUMN ebene TEXT",
    ],
}


def get_connection() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _migrieren(con: sqlite3.Connection) -> None:
    for tabelle, anweisungen in _MIGRATIONEN.items():
        vorhandene_spalten = {row["name"] for row in con.execute(f"PRAGMA table_info({tabelle})")}
        for anweisung in anweisungen:
            spalte = anweisung.split("ADD COLUMN")[1].split()[0]
            if spalte not in vorhandene_spalten:
                con.execute(anweisung)


def init_db() -> None:
    con = get_connection()
    try:
        con.executescript(_SCHEMA)
        _migrieren(con)
        con.commit()
    finally:
        con.close()


def jetzt() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
