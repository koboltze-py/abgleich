"""
Datenzugriff für Dienste (Stärkemeldungs-Einträge).
"""
from database.db import get_connection


def get_dienste_fuer_monat(jahr: int, monat: int, quelle: str | None = None) -> list[dict]:
    """Alle Dienste, deren Start-Datum in den angegebenen Monat fällt.
    Optional auf eine Datenquelle (Stärkemeldung/Ursprungsplanung) eingeschränkt."""
    von = f"{jahr:04d}-{monat:02d}-01"
    bis_monat = monat + 1
    bis_jahr = jahr
    if bis_monat > 12:
        bis_monat = 1
        bis_jahr += 1
    bis = f"{bis_jahr:04d}-{bis_monat:02d}-01"

    bedingung = "d.datum >= ? AND d.datum < ?"
    parameter = [von, bis]
    if quelle:
        bedingung += " AND d.quelle = ?"
        parameter.append(quelle)

    con = get_connection()
    try:
        rows = con.execute(
            f"""
            SELECT d.id, m.name AS mitarbeiter, d.quelle, d.kategorie, d.ebene, d.datum, d.start_zeit,
                   d.end_zeit, d.end_datum, d.dauer_minuten, dok.dateiname
            FROM dienste d
            JOIN mitarbeiter m ON m.id = d.mitarbeiter_id
            JOIN dokumente dok ON dok.id = d.dokument_id
            WHERE {bedingung}
            ORDER BY d.datum, d.start_zeit, m.name
            """,
            parameter,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def get_verfuegbare_monate(quelle: str | None = None) -> list[tuple[int, int]]:
    """Liste (Jahr, Monat) für die Daten vorhanden sind, neueste zuerst.
    Optional auf eine Datenquelle eingeschränkt."""
    bedingung = "WHERE quelle = ?" if quelle else ""
    parameter = [quelle] if quelle else []
    con = get_connection()
    try:
        rows = con.execute(
            f"SELECT DISTINCT substr(datum, 1, 7) AS ym FROM dienste {bedingung} ORDER BY ym DESC",
            parameter,
        ).fetchall()
        ergebnis = []
        for r in rows:
            jahr, monat = r["ym"].split("-")
            ergebnis.append((int(jahr), int(monat)))
        return ergebnis
    finally:
        con.close()


def get_kategorien(quelle: str | None = None) -> list[str]:
    bedingung = "WHERE quelle = ?" if quelle else ""
    parameter = [quelle] if quelle else []
    con = get_connection()
    try:
        rows = con.execute(
            f"SELECT DISTINCT kategorie FROM dienste {bedingung} ORDER BY kategorie", parameter
        ).fetchall()
        return [r["kategorie"] for r in rows]
    finally:
        con.close()


def get_quellen() -> list[str]:
    """Liste der Datenquellen (z. B. Stärkemeldung, Ursprungsplanung), für die Dienste vorliegen."""
    con = get_connection()
    try:
        rows = con.execute("SELECT DISTINCT quelle FROM dienste ORDER BY quelle").fetchall()
        return [r["quelle"] for r in rows]
    finally:
        con.close()


def get_dashboard_stats() -> dict:
    con = get_connection()
    try:
        anzahl_mitarbeiter = con.execute("SELECT COUNT(*) AS c FROM mitarbeiter").fetchone()["c"]
        anzahl_dienste = con.execute("SELECT COUNT(*) AS c FROM dienste").fetchone()["c"]
        anzahl_dokumente = con.execute("SELECT COUNT(*) AS c FROM dokumente").fetchone()["c"]
        letzter_import = con.execute(
            "SELECT MAX(importiert_am) AS x FROM dokumente"
        ).fetchone()["x"]
        letzter_tag = con.execute("SELECT MAX(datum) AS x FROM dienste").fetchone()["x"]
        return {
            "anzahl_mitarbeiter": anzahl_mitarbeiter,
            "anzahl_dienste": anzahl_dienste,
            "anzahl_dokumente": anzahl_dokumente,
            "letzter_import": letzter_import,
            "letzter_tag": letzter_tag,
        }
    finally:
        con.close()
