"""
Abgleich-Service: vergleicht die Ursprungsplanung (Excel) mit den tatsächlich
geleisteten Tagesdienstplänen (Stärkemeldung) je Mitarbeiter und Tag und
verwaltet den Bearbeitungs-Workflow (offen/erledigt je Änderung, zuletzt
bearbeiteter Mitarbeiter je Monat).
"""
import re
from dataclasses import dataclass, field

from config import QUELLE_STAERKEMELDUNG, QUELLE_URSPRUNGSPLANUNG
from database.db import get_connection, jetzt

ART_HINZUGEFUEGT = "hinzugefuegt"
ART_ZEIT_GEAENDERT = "zeit_geaendert"
ART_ENTFALLEN = "entfallen"

STATUS_OFFEN = "offen"
STATUS_ERLEDIGT = "erledigt"

_INITIALE_RE = re.compile(r"^[A-ZÄÖÜ]\.?$")


def _nachname_schluessel(name: str) -> str:
    """Extrahiert einen Nachnamen-Schlüssel aus unterschiedlichen Namensformaten
    ("Nachname, Vorname", "Nachname V.", "Vorname Nachname", nur "Nachname"),
    damit dieselbe Person trotz unterschiedlicher Schreibweise in Ursprungs-
    planung und Tagesdienstplänen als ein Mitarbeiter erkannt wird."""
    name = name.strip()
    if "," in name:
        return name.split(",", 1)[0].strip().lower()
    tokens = name.split()
    if not tokens:
        return name.lower()
    if len(tokens) == 1:
        return tokens[0].lower()
    if _INITIALE_RE.match(tokens[-1]):
        return " ".join(tokens[:-1]).lower()  # "Nachname V."
    return tokens[-1].lower()  # "Vorname Nachname" -> letztes Wort ist der Nachname


def _namens_vollstaendigkeit(name: str) -> int:
    """Bewertet, wie aussagekräftig ein Name ist (für die Anzeige des
    zusammengeführten Mitarbeiters wird die aussagekräftigste Variante gewählt)."""
    if "," in name:
        return 2
    tokens = name.split()
    if len(tokens) >= 2 and not _INITIALE_RE.match(tokens[-1]):
        return 2
    if len(tokens) >= 2:
        return 1
    return 0


@dataclass
class AbgleichEintrag:
    datum: str
    art: str
    alt_start: str | None = None
    alt_end: str | None = None
    neu_start: str | None = None
    neu_end: str | None = None
    status: str = STATUS_OFFEN


@dataclass
class MitarbeiterAbgleich:
    mitarbeiter_id: int
    name: str
    eintraege: list[AbgleichEintrag] = field(default_factory=list)
    nur_ursprungsplanung: bool = False  # keine Stärkemeldung-Daten im ganzen Monat gefunden
    nur_staerkemeldung: bool = False    # keine Ursprungsplanung-Daten im ganzen Monat gefunden

    @property
    def anzahl_offen(self) -> int:
        return sum(1 for e in self.eintraege if e.status == STATUS_OFFEN)

    @property
    def anzahl_gesamt(self) -> int:
        return len(self.eintraege)

    @property
    def kein_gegenstueck(self) -> bool:
        return self.nur_ursprungsplanung or self.nur_staerkemeldung


@dataclass
class AbgleichErgebnis:
    jahr: int
    monat: int
    mitarbeiter: list[MitarbeiterAbgleich]


def _monatsgrenzen(jahr: int, monat: int) -> tuple[str, str]:
    von = f"{jahr:04d}-{monat:02d}-01"
    bis_monat, bis_jahr = (monat + 1, jahr) if monat < 12 else (1, jahr + 1)
    bis = f"{bis_jahr:04d}-{bis_monat:02d}-01"
    return von, bis


def berechne_abgleich(jahr: int, monat: int) -> AbgleichErgebnis:
    """Vergleicht je Mitarbeiter und Tag die Ursprungsplanung mit den
    Tagesdienstplänen. Mitarbeiter werden dabei anhand des Nachnamens
    zusammengeführt, auch wenn Ursprungsplanung und Tagesdienstpläne den
    Namen unterschiedlich geschrieben haben (z. B. "Adrovic A." vs.
    "Adrian Adrovic" vs. nur "Adrovic"). Mitarbeiter ohne Abweichungen
    werden nicht aufgeführt."""
    von, bis = _monatsgrenzen(jahr, monat)
    con = get_connection()
    try:
        rows = con.execute(
            """
            SELECT d.mitarbeiter_id, m.name AS mitarbeiter, d.quelle, d.datum, d.start_zeit, d.end_zeit
            FROM dienste d
            JOIN mitarbeiter m ON m.id = d.mitarbeiter_id
            WHERE d.datum >= ? AND d.datum < ?
            """,
            (von, bis),
        ).fetchall()

        status_rows = con.execute(
            "SELECT mitarbeiter_id, datum, art, status FROM abgleich_status"
        ).fetchall()
    finally:
        con.close()

    # Zeilen anhand des Nachnamen-Schlüssels zu einer Person zusammenführen,
    # unabhängig davon, unter welcher mitarbeiter_id/Schreibweise sie in den
    # beiden Quellen jeweils gespeichert sind.
    gruppen_ids: dict[str, set[int]] = {}
    gruppen_namen: dict[str, set[str]] = {}
    up_tage: dict[str, dict[str, list[tuple[str, str]]]] = {}
    sm_tage: dict[str, dict[str, list[tuple[str, str]]]] = {}
    up_schluessel: set[str] = set()
    sm_schluessel: set[str] = set()

    for r in rows:
        schluessel = _nachname_schluessel(r["mitarbeiter"])
        gruppen_ids.setdefault(schluessel, set()).add(r["mitarbeiter_id"])
        gruppen_namen.setdefault(schluessel, set()).add(r["mitarbeiter"])
        ziel = up_tage if r["quelle"] == QUELLE_URSPRUNGSPLANUNG else sm_tage
        ziel_schluessel = up_schluessel if r["quelle"] == QUELLE_URSPRUNGSPLANUNG else sm_schluessel
        ziel_schluessel.add(schluessel)
        ziel.setdefault(schluessel, {}).setdefault(r["datum"], []).append((r["start_zeit"], r["end_zeit"]))

    status_lookup = {(r["mitarbeiter_id"], r["datum"], r["art"]): r["status"] for r in status_rows}

    ergebnis: list[MitarbeiterAbgleich] = []
    for schluessel in sorted(up_schluessel | sm_schluessel):
        up_pro_tag = up_tage.get(schluessel, {})
        sm_pro_tag = sm_tage.get(schluessel, {})
        alle_tage = sorted(set(up_pro_tag) | set(sm_pro_tag))

        eintraege: list[AbgleichEintrag] = []
        for tag in alle_tage:
            up_liste = list(up_pro_tag.get(tag, []))
            sm_liste = list(sm_pro_tag.get(tag, []))

            # identische Zeiten (unverändert) aus beiden Listen entfernen
            for paar in list(up_liste):
                if paar in sm_liste:
                    up_liste.remove(paar)
                    sm_liste.remove(paar)

            anzahl_paare = min(len(up_liste), len(sm_liste))
            for i in range(anzahl_paare):
                alt_start, alt_end = up_liste[i]
                neu_start, neu_end = sm_liste[i]
                eintraege.append(AbgleichEintrag(
                    datum=tag, art=ART_ZEIT_GEAENDERT,
                    alt_start=alt_start, alt_end=alt_end,
                    neu_start=neu_start, neu_end=neu_end,
                ))
            for alt_start, alt_end in up_liste[anzahl_paare:]:
                eintraege.append(AbgleichEintrag(
                    datum=tag, art=ART_ENTFALLEN, alt_start=alt_start, alt_end=alt_end,
                ))
            for neu_start, neu_end in sm_liste[anzahl_paare:]:
                eintraege.append(AbgleichEintrag(
                    datum=tag, art=ART_HINZUGEFUEGT, neu_start=neu_start, neu_end=neu_end,
                ))

        if not eintraege:
            continue  # kein Unterschied -> nicht Teil des Abarbeitungs-Workflows

        # kanonische mitarbeiter_id (kleinste id der Gruppe) für Statuspersistenz
        canonical_id = min(gruppen_ids[schluessel])
        anzeige_name = max(gruppen_namen[schluessel], key=lambda n: (_namens_vollstaendigkeit(n), len(n)))

        for e in eintraege:
            e.status = status_lookup.get((canonical_id, e.datum, e.art), STATUS_OFFEN)

        ergebnis.append(MitarbeiterAbgleich(
            mitarbeiter_id=canonical_id, name=anzeige_name, eintraege=eintraege,
            nur_ursprungsplanung=schluessel in up_schluessel and schluessel not in sm_schluessel,
            nur_staerkemeldung=schluessel in sm_schluessel and schluessel not in up_schluessel,
        ))

    ergebnis.sort(key=lambda ma: ma.name.lower())
    return AbgleichErgebnis(jahr=jahr, monat=monat, mitarbeiter=ergebnis)


def set_eintrag_status(mitarbeiter_id: int, datum: str, art: str, status: str) -> None:
    con = get_connection()
    try:
        con.execute(
            """
            INSERT INTO abgleich_status (mitarbeiter_id, datum, art, status, bearbeitet_am)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(mitarbeiter_id, datum, art)
            DO UPDATE SET status = excluded.status, bearbeitet_am = excluded.bearbeitet_am
            """,
            (mitarbeiter_id, datum, art, status, jetzt()),
        )
        con.commit()
    finally:
        con.close()


def set_status_fuer_mitarbeiter(mitarbeiter_id: int, eintraege: list[AbgleichEintrag], status: str) -> None:
    """Setzt den Status für mehrere Änderungen desselben Mitarbeiters auf einmal
    (z. B. 'alle als erledigt markieren')."""
    con = get_connection()
    try:
        zeit = jetzt()
        con.executemany(
            """
            INSERT INTO abgleich_status (mitarbeiter_id, datum, art, status, bearbeitet_am)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(mitarbeiter_id, datum, art)
            DO UPDATE SET status = excluded.status, bearbeitet_am = excluded.bearbeitet_am
            """,
            [(mitarbeiter_id, e.datum, e.art, status, zeit) for e in eintraege],
        )
        con.commit()
    finally:
        con.close()


def get_letzte_position(jahr: int, monat: int) -> int | None:
    """Liefert die mitarbeiter_id, bei der der Abgleich zuletzt bearbeitet wurde."""
    con = get_connection()
    try:
        row = con.execute(
            "SELECT mitarbeiter_id FROM abgleich_fortschritt WHERE jahr = ? AND monat = ?",
            (jahr, monat),
        ).fetchone()
        return row["mitarbeiter_id"] if row else None
    finally:
        con.close()


def set_letzte_position(jahr: int, monat: int, mitarbeiter_id: int) -> None:
    con = get_connection()
    try:
        con.execute(
            """
            INSERT INTO abgleich_fortschritt (jahr, monat, mitarbeiter_id, aktualisiert_am)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(jahr, monat) DO UPDATE SET mitarbeiter_id = excluded.mitarbeiter_id,
                                                    aktualisiert_am = excluded.aktualisiert_am
            """,
            (jahr, monat, mitarbeiter_id, jetzt()),
        )
        con.commit()
    finally:
        con.close()


def get_verfuegbare_monate() -> list[tuple[int, int]]:
    """Monate, für die sowohl Ursprungsplanung als auch Tagesdienstpläne vorliegen
    (nur für diese ist ein sinnvoller Abgleich möglich)."""
    con = get_connection()
    try:
        rows = con.execute(
            "SELECT DISTINCT substr(datum, 1, 7) AS ym, quelle FROM dienste"
        ).fetchall()
    finally:
        con.close()

    monate_je_quelle: dict[str, set[str]] = {}
    for r in rows:
        monate_je_quelle.setdefault(r["quelle"], set()).add(r["ym"])

    gemeinsam = monate_je_quelle.get(QUELLE_URSPRUNGSPLANUNG, set()) & monate_je_quelle.get(QUELLE_STAERKEMELDUNG, set())
    ergebnis = [(int(ym.split("-")[0]), int(ym.split("-")[1])) for ym in gemeinsam]
    return sorted(ergebnis, reverse=True)
