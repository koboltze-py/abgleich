"""
Datenzugriff und Pflege für Mitarbeiter (Umbenennen, Zusammenführen von Dubletten).
"""
from database.db import get_connection


def list_mitarbeiter(jahr: int = None, monat: int = None) -> list[dict]:
    """Liefert alle Mitarbeiter mit Dienst-Statistik, optional gefiltert auf einen Monat."""
    con = get_connection()
    try:
        if jahr and monat:
            von = f"{jahr:04d}-{monat:02d}-01"
            bm, by = (monat + 1, jahr) if monat < 12 else (1, jahr + 1)
            bis = f"{by:04d}-{bm:02d}-01"
            rows = con.execute(
                """
                SELECT m.id, m.name, m.aktiv,
                       COUNT(d.id) AS anzahl_dienste,
                       COALESCE(SUM(d.dauer_minuten), 0) AS summe_minuten
                FROM mitarbeiter m
                LEFT JOIN dienste d ON d.mitarbeiter_id = m.id AND d.datum >= ? AND d.datum < ?
                GROUP BY m.id
                ORDER BY m.name COLLATE NOCASE
                """,
                (von, bis),
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT m.id, m.name, m.aktiv,
                       COUNT(d.id) AS anzahl_dienste,
                       COALESCE(SUM(d.dauer_minuten), 0) AS summe_minuten
                FROM mitarbeiter m
                LEFT JOIN dienste d ON d.mitarbeiter_id = m.id
                GROUP BY m.id
                ORDER BY m.name COLLATE NOCASE
                """
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def rename_mitarbeiter(mitarbeiter_id: int, neuer_name: str) -> None:
    neuer_name = neuer_name.strip()
    if not neuer_name:
        raise ValueError("Name darf nicht leer sein")
    con = get_connection()
    try:
        con.execute("UPDATE mitarbeiter SET name = ? WHERE id = ?", (neuer_name, mitarbeiter_id))
        con.commit()
    finally:
        con.close()


def merge_mitarbeiter(quelle_id: int, ziel_id: int) -> None:
    """Verschiebt alle Dienste von 'quelle_id' zu 'ziel_id' und löscht den Quell-Mitarbeiter."""
    if quelle_id == ziel_id:
        raise ValueError("Quelle und Ziel dürfen nicht identisch sein")
    con = get_connection()
    try:
        con.execute(
            "UPDATE dienste SET mitarbeiter_id = ? WHERE mitarbeiter_id = ?", (ziel_id, quelle_id)
        )
        con.execute("DELETE FROM mitarbeiter WHERE id = ?", (quelle_id,))
        con.commit()
    finally:
        con.close()
