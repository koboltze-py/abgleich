"""
Abgleich-Service: vergleicht die Ursprungsplanung (Excel) mit den tatsächlich
geleisteten Tagesdienstplänen (Stärkemeldung) je Mitarbeiter und Tag und
verwaltet den Bearbeitungs-Workflow (offen/erledigt je Änderung, zuletzt
bearbeiteter Mitarbeiter je Monat).
"""
import re
from dataclasses import dataclass, field
from itertools import permutations

from config import QUELLE_STAERKEMELDUNG, QUELLE_URSPRUNGSPLANUNG
from database.db import get_connection, jetzt

ART_HINZUGEFUEGT = "hinzugefuegt"
ART_ZEIT_GEAENDERT = "zeit_geaendert"
ART_ENTFALLEN = "entfallen"

STATUS_OFFEN = "offen"
STATUS_ERLEDIGT = "erledigt"

_INITIALE_RE = re.compile(r"^[A-ZÄÖÜ]\.?$")


def _komponenten(name: str) -> list[str]:
    """Zerlegt einen Namen in seine Bestandteile, unabhängig von der Reihenfolge
    (Nachname zuerst/zuletzt) und davon, welcher Teil abgekürzt wurde."""
    name = name.strip()
    if "," in name:
        return [t.strip() for t in name.split(",", 1) if t.strip()]
    return name.split()


def _ist_kurzform(komponente: str) -> bool:
    """Kürzel wie "A", "A.", "Em", "Ek" (Tagesdienstpläne kürzen Vor- ODER
    Nachname unterschiedlich stark ab) - alles bis 2 Buchstaben (ohne Punkt)."""
    return len(komponente.rstrip(".")) <= 2


def _komponenten_kompatibel(a: str, b: str) -> bool:
    a, b = a.lower().rstrip("."), b.lower().rstrip(".")
    if a == b:
        return True
    if _ist_kurzform(a) and b.startswith(a):
        return True
    if _ist_kurzform(b) and a.startswith(b):
        return True
    return False


def _namen_gleiche_person(komponenten_a: list[str], komponenten_b: list[str]) -> bool:
    """Prüft, ob sich die (kürzere) Komponentenliste vollständig und eindeutig
    auf unterschiedliche Komponenten der anderen Liste abbilden lässt (z. B.
    "Bakkal"+"Em" auf "Emirhan"+"Bakkal", aber NICHT auf "Kerim"+"Bakkal")."""
    if not komponenten_a or not komponenten_b:
        return False
    kurze, lange = (komponenten_a, komponenten_b) if len(komponenten_a) <= len(komponenten_b) else (komponenten_b, komponenten_a)
    # Ein einzelner, vollständiger Namensbestandteil (z. B. bloßer Nachname
    # "Adrovic") darf nur auf einen ebenfalls vollständigen Bestandteil der
    # Gegenseite treffen - sonst würde ein zufälliges 2-Buchstaben-Präfix
    # (z. B. "Kedik" vs. das Kürzel "Ke" in "Bakkal Ke") einen falschen Treffer erzeugen.
    einzeln_vollstaendig = len(kurze) == 1 and not _ist_kurzform(kurze[0])
    for auswahl in permutations(range(len(lange)), len(kurze)):
        if einzeln_vollstaendig and _ist_kurzform(lange[auswahl[0]]):
            continue
        if all(_komponenten_kompatibel(kurze[i], lange[auswahl[i]]) for i in range(len(kurze))):
            return True
    return False


def _namens_vollstaendigkeit(name: str) -> int:
    """Bewertet, wie aussagekräftig ein Name ist (für die Anzeige des
    zusammengeführten Mitarbeiters wird die aussagekräftigste Variante gewählt)."""
    komponenten = _komponenten(name)
    if len(komponenten) >= 2 and not any(_ist_kurzform(k) for k in komponenten):
        return 2
    if len(komponenten) >= 2:
        return 1
    return 0


def _namen_gruppieren(namen: list[str]) -> dict[str, int]:
    """Führt unterschiedlich geschriebene Namen zusammen, die vermutlich
    dieselbe Person meinen - aber nur, wenn die Zuordnung eindeutig ist.

    Baut einen Kompatibilitätsgraphen und fasst jede zusammenhängende
    Namensgruppe zu einer Person zusammen, WENN diese Gruppe eine Clique ist
    (jeder Name ist mit jedem anderen kompatibel). Ist das nicht der Fall,
    verbindet vermutlich ein mehrdeutiger "Sammel"-Name (z. B. nur ein
    Nachname wie "El Karfouh" oder nur ein Vorname wie "Tunahan", der auf
    mehrere unterschiedliche Personen passen könnte) zwei eigentlich getrennte
    Personen. Ein solcher Knoten (der mit den meisten anderen in der Gruppe
    kompatibel ist) wird isoliert und bleibt als eigener, zu prüfender
    Mismatch stehen; der Rest wird rekursiv neu aufgeteilt."""
    eindeutige_namen = list(dict.fromkeys(namen))
    komponenten = {n: _komponenten(n) for n in eindeutige_namen}

    kompatibel: dict[str, set[str]] = {n: set() for n in eindeutige_namen}
    for i, a in enumerate(eindeutige_namen):
        for b in eindeutige_namen[i + 1:]:
            if _namen_gleiche_person(komponenten[a], komponenten[b]):
                kompatibel[a].add(b)
                kompatibel[b].add(a)

    gruppen_index: dict[str, int] = {}
    naechster_index = 0

    def zusammenhang_finden(start: str, uebrig: set[str]) -> set[str]:
        besucht = {start}
        stapel = [start]
        while stapel:
            n = stapel.pop()
            for m in kompatibel[n] & uebrig:
                if m not in besucht:
                    besucht.add(m)
                    stapel.append(m)
        return besucht

    def ist_clique(knoten: set[str]) -> bool:
        return all((knoten - {n}) <= kompatibel[n] for n in knoten)

    def verarbeiten(knoten: set[str]) -> None:
        nonlocal naechster_index
        if not knoten:
            return
        if len(knoten) == 1 or ist_clique(knoten):
            for n in knoten:
                gruppen_index[n] = naechster_index
            naechster_index += 1
            return
        # kein eindeutiger Fall: den am stärksten vernetzten (vermutlich
        # mehrdeutigen) Knoten isolieren und den Rest neu aufteilen. Bei Gleichstand
        # wird alphabetisch entschieden, damit das Ergebnis reproduzierbar ist
        # (unabhängig von der zufallsseed-abhängigen set-Reihenfolge).
        hub = max(sorted(knoten), key=lambda n: len(kompatibel[n] & knoten))
        gruppen_index[hub] = naechster_index
        naechster_index += 1
        rest = knoten - {hub}
        while rest:
            teil = zusammenhang_finden(min(rest), rest)
            rest -= teil
            verarbeiten(teil)

    unbesucht = set(eindeutige_namen)
    while unbesucht:
        komponente = zusammenhang_finden(min(unbesucht), unbesucht)
        unbesucht -= komponente
        verarbeiten(komponente)

    return gruppen_index


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
    Tagesdienstplänen. Mitarbeiter werden dabei anhand ihrer Namensbestandteile
    zusammengeführt, auch wenn Ursprungsplanung und Tagesdienstpläne den Namen
    unterschiedlich geschrieben oder unterschiedlich stark abgekürzt haben
    (z. B. "Adrovic A." vs. "Adrian Adrovic" vs. nur "Adrovic", oder
    "Bakkal Em" vs. "Emirhan Bakkal"). Mehrdeutige Namen (z. B. nur "Tunahan",
    wenn es zwei unterschiedliche Personen mit Vorname Tunahan gibt) werden
    NICHT geraten, sondern bleiben als eigener Mismatch stehen. Mitarbeiter
    ohne Abweichungen werden nicht aufgeführt."""
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

    # Rohnamen zu Gruppen (vermutlich dieselbe Person) zusammenführen,
    # unabhängig davon, unter welcher mitarbeiter_id/Schreibweise sie in den
    # beiden Quellen jeweils gespeichert sind.
    gruppe_je_name = _namen_gruppieren([r["mitarbeiter"] for r in rows])

    gruppen_ids: dict[int, set[int]] = {}
    gruppen_namen: dict[int, set[str]] = {}
    up_tage: dict[int, dict[str, list[tuple[str, str]]]] = {}
    sm_tage: dict[int, dict[str, list[tuple[str, str]]]] = {}
    up_gruppen: set[int] = set()
    sm_gruppen: set[int] = set()

    for r in rows:
        gruppe = gruppe_je_name[r["mitarbeiter"]]
        gruppen_ids.setdefault(gruppe, set()).add(r["mitarbeiter_id"])
        gruppen_namen.setdefault(gruppe, set()).add(r["mitarbeiter"])
        ziel = up_tage if r["quelle"] == QUELLE_URSPRUNGSPLANUNG else sm_tage
        ziel_gruppen = up_gruppen if r["quelle"] == QUELLE_URSPRUNGSPLANUNG else sm_gruppen
        ziel_gruppen.add(gruppe)
        ziel.setdefault(gruppe, {}).setdefault(r["datum"], []).append((r["start_zeit"], r["end_zeit"]))

    status_lookup = {(r["mitarbeiter_id"], r["datum"], r["art"]): r["status"] for r in status_rows}

    ergebnis: list[MitarbeiterAbgleich] = []
    for gruppe in sorted(up_gruppen | sm_gruppen):
        up_pro_tag = up_tage.get(gruppe, {})
        sm_pro_tag = sm_tage.get(gruppe, {})
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
        canonical_id = min(gruppen_ids[gruppe])
        anzeige_name = max(gruppen_namen[gruppe], key=lambda n: (_namens_vollstaendigkeit(n), len(n)))

        for e in eintraege:
            e.status = status_lookup.get((canonical_id, e.datum, e.art), STATUS_OFFEN)

        ergebnis.append(MitarbeiterAbgleich(
            mitarbeiter_id=canonical_id, name=anzeige_name, eintraege=eintraege,
            nur_ursprungsplanung=gruppe in up_gruppen and gruppe not in sm_gruppen,
            nur_staerkemeldung=gruppe in sm_gruppen and gruppe not in up_gruppen,
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
