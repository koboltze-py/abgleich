"""
Abgleich-Service: vergleicht die Ursprungsplanung (Excel) mit den tatsächlich
geleisteten Tagesdienstplänen (Stärkemeldung) je Mitarbeiter und Tag und
verwaltet den Bearbeitungs-Workflow (offen/erledigt je Änderung, zuletzt
bearbeiteter Mitarbeiter je Monat).
"""
import calendar
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import permutations

from config import QUELLE_STAERKEMELDUNG, QUELLE_URSPRUNGSPLANUNG
from database.db import get_connection, jetzt

ART_HINZUGEFUEGT = "hinzugefuegt"
ART_ZEIT_GEAENDERT = "zeit_geaendert"
ART_ENTFALLEN = "entfallen"
ART_UNVERAENDERT = "unveraendert"
ART_KEINE_DATEN = "keine_daten"

STATUS_OFFEN = "offen"
STATUS_ERLEDIGT = "erledigt"

_MANUELLER_DOKUMENT_PFAD = "__manuelle_eingabe_abgleich__"
_ZEIT_BEREICH_RE = re.compile(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$")

_INITIALE_RE = re.compile(r"^[A-ZÄÖÜ]\.?$")


def _komponenten(name: str) -> list[str]:
    """Zerlegt einen Namen in seine Bestandteile, unabhängig von der Reihenfolge
    (Nachname zuerst/zuletzt) und davon, welcher Teil abgekürzt wurde."""
    name = name.strip()
    if "," in name:
        return [t.strip() for t in name.split(",", 1) if t.strip()]
    return name.split()


def _ist_kurzform(komponente: str) -> bool:
    """Kürzel wie "A", "A.", "Em", "Ek" - bis 2 Buchstaben (ohne Punkt)."""
    return len(komponente.rstrip(".")) <= 2


def _kurzform_maske(komponenten: list[str]) -> list[bool]:
    """Laut Konvention der Tagesdienstpläne wird bei doppelten Nachnamen immer
    NUR der Vorname gekürzt, und zwar als letztes Wort des Namens. Das erste
    Wort (bzw. ein alleinstehendes Wort) ist deshalb IMMER der vollständige
    Nachname - auch wenn dieser selbst kurz ist (z. B. echte 2-Buchstaben-
    Nachnamen wie "Su", "Oh"). Nur die letzte Komponente eines mehrteiligen
    Namens kann also als Kürzel gelten."""
    maske = [False] * len(komponenten)
    if len(komponenten) >= 2 and _ist_kurzform(komponenten[-1]):
        maske[-1] = True
    return maske


def _komponenten_kompatibel(a: str, a_kurz: bool, b: str, b_kurz: bool) -> bool:
    a, b = a.lower().rstrip("."), b.lower().rstrip(".")
    if a == b:
        return True
    if a_kurz and b_kurz:
        return a.startswith(b) or b.startswith(a)
    # Ein Kürzel darf nur auf ein wirklich VOLLSTÄNDIGES Wort treffen (mehr als
    # 2 Buchstaben) - sonst wären zwei zufällig kurze Wörter (z. B. der echte
    # Nachname "Su" und das Kürzel "S." eines ANDEREN Namens) ununterscheidbar.
    if a_kurz and not b_kurz:
        return len(b) > 2 and b.startswith(a)
    if b_kurz and not a_kurz:
        return len(a) > 2 and a.startswith(b)
    return False


def _namen_gleiche_person(komponenten_a: list[str], komponenten_b: list[str]) -> bool:
    """Prüft, ob sich die (kürzere) Komponentenliste vollständig und eindeutig
    auf unterschiedliche Komponenten der anderen Liste abbilden lässt (z. B.
    "Bakkal"+"Em" auf "Emirhan"+"Bakkal", aber NICHT auf "Kerim"+"Bakkal")."""
    if not komponenten_a or not komponenten_b:
        return False
    kurze, lange = (komponenten_a, komponenten_b) if len(komponenten_a) <= len(komponenten_b) else (komponenten_b, komponenten_a)
    kurze_maske = _kurzform_maske(kurze)
    lange_maske = _kurzform_maske(lange)
    # Ein einzelner Namensbestandteil (kein zweites Wort zur Bestätigung, z. B.
    # bloßer Nachname "Adrovic" oder "Su") darf nur auf ein ebenfalls
    # vollständiges (nicht gekürztes) Wort der Gegenseite treffen - sonst würde
    # ein zufälliges Präfix (z. B. "Kedik" vs. das Kürzel "Ke" in "Bakkal Ke",
    # oder "Su" vs. das Kürzel in "Suna O.") einen falschen Treffer erzeugen.
    nur_volles_ziel_erlaubt = len(kurze) == 1
    letzter_index = len(lange) - 1
    for auswahl in permutations(range(len(lange)), len(kurze)):
        if nur_volles_ziel_erlaubt and lange_maske[auswahl[0]]:
            continue
        # Ein Kürzel (Vorname-Abkürzung) darf nur an den Rand des anderen
        # Namens andocken (erstes oder letztes Wort), niemals mitten in einen
        # mehrteiligen Nachnamen hinein (sonst würde z. B. "Bakkal K." über
        # "K." fälschlich auf das mittlere Wort "Karfouh" in "El Karfouh B." treffen).
        if any(
            kurze_maske[i] and 0 < auswahl[i] < letzter_index
            for i in range(len(kurze))
        ):
            continue
        if all(
            _komponenten_kompatibel(kurze[i], kurze_maske[i], lange[auswahl[i]], lange_maske[auswahl[i]])
            for i in range(len(kurze))
        ):
            return True
    return False


def _namens_vollstaendigkeit(name: str) -> int:
    """Bewertet, wie aussagekräftig ein Name ist (für die Anzeige des
    zusammengeführten Mitarbeiters wird die aussagekräftigste Variante gewählt)."""
    komponenten = _komponenten(name)
    if len(komponenten) >= 2 and not any(_kurzform_maske(komponenten)):
        return 2
    if len(komponenten) >= 2:
        return 1
    return 0


def _namen_gruppieren(namen: list[str], getrennt: set[frozenset] | None = None) -> dict[str, int]:
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
    Mismatch stehen; der Rest wird rekursiv neu aufgeteilt.

    `getrennt` sind vom Nutzer erzwungene Namenspaare, die NIE als dieselbe
    Person gelten sollen, selbst wenn sie sonst kompatibel wären."""
    eindeutige_namen = list(dict.fromkeys(namen))
    komponenten = {n: _komponenten(n) for n in eindeutige_namen}
    getrennt = getrennt or set()

    kompatibel: dict[str, set[str]] = {n: set() for n in eindeutige_namen}
    for i, a in enumerate(eindeutige_namen):
        for b in eindeutige_namen[i + 1:]:
            if frozenset((a, b)) in getrennt:
                continue
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
    varianten: list[str] = field(default_factory=list)  # alle zusammengeführten Rohnamen
    mitarbeiter_ids: list[int] = field(default_factory=list)  # alle zusammengeführten mitarbeiter_id
    mitglieder: list[tuple[str, int]] = field(default_factory=list)  # (Rohname, mitarbeiter_id) je Variante
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


@dataclass
class TagesZeile:
    """Ein einzelner Tag im vollen Monats-Editor eines Mitarbeiters (auch Tage
    ohne jede Abweichung oder ganz ohne Daten in einer der beiden Quellen)."""
    datum: str
    ursprung_start: str | None = None
    ursprung_end: str | None = None
    tatsaechlich_start: str | None = None
    tatsaechlich_end: str | None = None
    art: str = ART_KEINE_DATEN
    status: str = STATUS_OFFEN


def zeit_bereich_parsen(text: str) -> tuple[str, str] | None:
    """Parst eine von Hand eingegebene Zeit wie "07:00-15:00". Gibt None bei
    leerem Text zurück, wirft ValueError bei ungültigem Format."""
    text = text.strip()
    if not text:
        return None
    treffer = _ZEIT_BEREICH_RE.match(text)
    if not treffer:
        raise ValueError(f"Ungültiges Format: {text!r} (erwartet z. B. \"07:00-15:00\")")
    sh, sm, eh, em = (int(t) for t in treffer.groups())
    if sh > 23 or eh > 23 or sm > 59 or em > 59:
        raise ValueError(f"Ungültige Uhrzeit: {text!r}")
    return f"{sh:02d}:{sm:02d}", f"{eh:02d}:{em:02d}"


def monatsplan_fuer_mitarbeiter(jahr: int, monat: int, mitarbeiter_ids: list[int]) -> list[TagesZeile]:
    """Liefert für einen Mitarbeiter (bzw. alle zusammengeführten mitarbeiter_id
    einer Identität) JEDEN Tag des Monats - auch Tage ganz ohne Daten in einer
    der beiden Quellen, damit sie direkt von Hand nachgetragen werden können."""
    if not mitarbeiter_ids:
        return []
    von, bis = _monatsgrenzen(jahr, monat)
    platzhalter = ",".join("?" * len(mitarbeiter_ids))
    con = get_connection()
    try:
        rows = con.execute(
            f"""
            SELECT quelle, datum, start_zeit, end_zeit FROM dienste
            WHERE mitarbeiter_id IN ({platzhalter}) AND datum >= ? AND datum < ?
            ORDER BY start_zeit
            """,
            (*mitarbeiter_ids, von, bis),
        ).fetchall()
        status_rows = con.execute(
            f"SELECT datum, art, status FROM abgleich_status WHERE mitarbeiter_id IN ({platzhalter})",
            mitarbeiter_ids,
        ).fetchall()
    finally:
        con.close()

    up_tage: dict[str, tuple[str, str]] = {}
    sm_tage: dict[str, tuple[str, str]] = {}
    for r in rows:
        ziel = up_tage if r["quelle"] == QUELLE_URSPRUNGSPLANUNG else sm_tage
        ziel.setdefault(r["datum"], (r["start_zeit"], r["end_zeit"]))

    status_lookup = {(r["datum"], r["art"]): r["status"] for r in status_rows}

    anzahl_tage = calendar.monthrange(jahr, monat)[1]
    ergebnis: list[TagesZeile] = []
    for tag in range(1, anzahl_tage + 1):
        datum = f"{jahr:04d}-{monat:02d}-{tag:02d}"
        up = up_tage.get(datum)
        sm = sm_tage.get(datum)

        if up is None and sm is None:
            art = ART_KEINE_DATEN
        elif up == sm:
            art = ART_UNVERAENDERT
        elif up is None:
            art = ART_HINZUGEFUEGT
        elif sm is None:
            art = ART_ENTFALLEN
        else:
            art = ART_ZEIT_GEAENDERT

        ergebnis.append(TagesZeile(
            datum=datum,
            ursprung_start=up[0] if up else None, ursprung_end=up[1] if up else None,
            tatsaechlich_start=sm[0] if sm else None, tatsaechlich_end=sm[1] if sm else None,
            art=art, status=status_lookup.get((datum, art), STATUS_OFFEN),
        ))
    return ergebnis


def _manueller_dokument_id(con) -> int:
    row = con.execute("SELECT id FROM dokumente WHERE dateipfad = ?", (_MANUELLER_DOKUMENT_PFAD,)).fetchone()
    if row:
        return row["id"]
    cur = con.execute(
        "INSERT INTO dokumente (dateipfad, dateiname, quelle, von_datum, bis_datum, importiert_am, anzahl_eintraege) "
        "VALUES (?, ?, ?, NULL, NULL, ?, 0)",
        (_MANUELLER_DOKUMENT_PFAD, "Manuelle Eingabe (Abgleich)", QUELLE_STAERKEMELDUNG, jetzt()),
    )
    return cur.lastrowid


def setze_manuellen_dienst(mitarbeiter_id: int, datum: str, zeit: tuple[str, str] | None) -> None:
    """Trägt für einen Tag die "Tatsächlich"-Zeit direkt in der Abgleich-Maske
    ein, ändert sie oder löscht sie (zeit=None). Ersetzt einen evtl. an diesem
    Tag bereits vorhandenen Stärkemeldung-Eintrag dieses Mitarbeiters."""
    con = get_connection()
    try:
        con.execute(
            "DELETE FROM dienste WHERE mitarbeiter_id = ? AND datum = ? AND quelle = ?",
            (mitarbeiter_id, datum, QUELLE_STAERKEMELDUNG),
        )
        if zeit is not None:
            start_zeit, end_zeit = zeit
            sh, sm = (int(t) for t in start_zeit.split(":"))
            eh, em = (int(t) for t in end_zeit.split(":"))
            start_dt = datetime.strptime(datum, "%Y-%m-%d").replace(hour=sh, minute=sm)
            end_dt = start_dt.replace(hour=eh, minute=em)
            if (eh, em) <= (sh, sm):
                end_dt += timedelta(days=1)
            dauer = int((end_dt - start_dt).total_seconds() // 60)
            dok_id = _manueller_dokument_id(con)
            con.execute(
                """
                INSERT INTO dienste (mitarbeiter_id, dokument_id, quelle, kategorie, datum,
                                      start_zeit, end_zeit, end_datum, dauer_minuten)
                VALUES (?, ?, ?, 'Manuell', ?, ?, ?, ?, ?)
                """,
                (mitarbeiter_id, dok_id, QUELLE_STAERKEMELDUNG, datum,
                 start_zeit, end_zeit, end_dt.strftime("%Y-%m-%d"), dauer),
            )
        con.commit()
    finally:
        con.close()


def _gruppen_fuer_monat(jahr: int, monat: int):
    """Lädt alle Dienst-Rohzeilen eines Monats und fasst sie (automatisch per
    Namensvergleich + manuelle Zuordnung/Trennung) zu Mitarbeiter-Identitäten
    zusammen. Rückgabe: (rows, gruppen_ids, gruppen_namen, up_gruppen,
    sm_gruppen, id_zu_gruppe). Wird sowohl von berechne_abgleich als auch von
    voller_monatsplan verwendet, damit beide dieselbe Gruppierung nutzen."""
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
        manuelle_paare = con.execute(
            "SELECT mitarbeiter_id_a, mitarbeiter_id_b FROM abgleich_manuelle_zuordnung"
        ).fetchall()
        trennungs_paare = con.execute(
            "SELECT mitarbeiter_id_a, mitarbeiter_id_b FROM abgleich_manuelle_trennung"
        ).fetchall()
    finally:
        con.close()

    id_zu_name: dict[int, str] = {r["mitarbeiter_id"]: r["mitarbeiter"] for r in rows}
    getrennt: set[frozenset] = set()
    for paar in trennungs_paare:
        na = id_zu_name.get(paar["mitarbeiter_id_a"])
        nb = id_zu_name.get(paar["mitarbeiter_id_b"])
        if na and nb:
            getrennt.add(frozenset((na, nb)))

    # Rohnamen zu Gruppen (vermutlich dieselbe Person) zusammenführen,
    # unabhängig davon, unter welcher mitarbeiter_id/Schreibweise sie in den
    # beiden Quellen jeweils gespeichert sind.
    gruppe_je_name = _namen_gruppieren([r["mitarbeiter"] for r in rows], getrennt=getrennt)

    # Manuelle Zuordnungen (vom Nutzer bestätigte Verknüpfungen, die die
    # automatische Erkennung nicht selbst gefunden hat) über die automatischen
    # Gruppen legen und ggf. mehrere Gruppen zu einer verschmelzen.
    gruppen_eltern: dict[int, int] = {g: g for g in set(gruppe_je_name.values())}

    def gfind(g: int) -> int:
        while gruppen_eltern[g] != g:
            gruppen_eltern[g] = gruppen_eltern[gruppen_eltern[g]]
            g = gruppen_eltern[g]
        return g

    def gunion(g1: int, g2: int) -> None:
        r1, r2 = gfind(g1), gfind(g2)
        if r1 != r2:
            gruppen_eltern[r1] = r2

    id_zu_gruppe_vorlaeufig: dict[int, int] = {r["mitarbeiter_id"]: gruppe_je_name[r["mitarbeiter"]] for r in rows}
    for paar in manuelle_paare:
        ga = id_zu_gruppe_vorlaeufig.get(paar["mitarbeiter_id_a"])
        gb = id_zu_gruppe_vorlaeufig.get(paar["mitarbeiter_id_b"])
        if ga is not None and gb is not None:
            gunion(ga, gb)

    gruppen_ids: dict[int, set[int]] = {}
    gruppen_namen: dict[int, set[str]] = {}
    up_gruppen: set[int] = set()
    sm_gruppen: set[int] = set()
    id_zu_gruppe: dict[int, int] = {}

    for r in rows:
        gruppe = gfind(gruppe_je_name[r["mitarbeiter"]])
        id_zu_gruppe[r["mitarbeiter_id"]] = gruppe
        gruppen_ids.setdefault(gruppe, set()).add(r["mitarbeiter_id"])
        gruppen_namen.setdefault(gruppe, set()).add(r["mitarbeiter"])
        ziel_gruppen = up_gruppen if r["quelle"] == QUELLE_URSPRUNGSPLANUNG else sm_gruppen
        ziel_gruppen.add(gruppe)

    return rows, gruppen_ids, gruppen_namen, up_gruppen, sm_gruppen, id_zu_gruppe


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
    rows, gruppen_ids, gruppen_namen, up_gruppen, sm_gruppen, id_zu_gruppe = _gruppen_fuer_monat(jahr, monat)

    con = get_connection()
    try:
        status_rows = con.execute(
            "SELECT mitarbeiter_id, datum, art, status FROM abgleich_status"
        ).fetchall()
    finally:
        con.close()

    up_tage: dict[int, dict[str, list[tuple[str, str]]]] = {}
    sm_tage: dict[int, dict[str, list[tuple[str, str]]]] = {}
    for r in rows:
        gruppe = id_zu_gruppe[r["mitarbeiter_id"]]
        ziel = up_tage if r["quelle"] == QUELLE_URSPRUNGSPLANUNG else sm_tage
        ziel.setdefault(gruppe, {}).setdefault(r["datum"], []).append((r["start_zeit"], r["end_zeit"]))

    id_zu_name: dict[int, str] = {r["mitarbeiter_id"]: r["mitarbeiter"] for r in rows}
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
        alle_ids = gruppen_ids[gruppe]
        canonical_id = min(alle_ids)
        # bei Punktgleichstand alphabetisch entscheiden, damit die Anzeige
        # reproduzierbar ist (unabhängig von der zufallsseed-abhängigen set-Reihenfolge)
        anzeige_name = max(
            sorted(gruppen_namen[gruppe]), key=lambda n: (_namens_vollstaendigkeit(n), len(n))
        )

        for e in eintraege:
            # alle IDs der Gruppe prüfen (nicht nur die kanonische), damit ein
            # Status auch nach nachträglichem manuellem Zusammenführen erhalten bleibt
            e.status = next(
                (status_lookup[(mid, e.datum, e.art)] for mid in alle_ids if (mid, e.datum, e.art) in status_lookup),
                STATUS_OFFEN,
            )

        ergebnis.append(MitarbeiterAbgleich(
            mitarbeiter_id=canonical_id, name=anzeige_name, eintraege=eintraege,
            varianten=sorted(gruppen_namen[gruppe], key=str.lower),
            mitarbeiter_ids=sorted(alle_ids),
            mitglieder=sorted(
                ((id_zu_name[mid], mid) for mid in alle_ids if mid in id_zu_name),
                key=lambda paar: paar[0].lower(),
            ),
            nur_ursprungsplanung=gruppe in up_gruppen and gruppe not in sm_gruppen,
            nur_staerkemeldung=gruppe in sm_gruppen and gruppe not in up_gruppen,
        ))

    ergebnis.sort(key=lambda ma: ma.name.lower())
    return AbgleichErgebnis(jahr=jahr, monat=monat, mitarbeiter=ergebnis)


@dataclass
class MitarbeiterMonatsplan:
    mitarbeiter_id: int
    name: str
    mitarbeiter_ids: list[int]
    tage: list[TagesZeile]


def voller_monatsplan(jahr: int, monat: int) -> list[MitarbeiterMonatsplan]:
    """Liefert für JEDEN Mitarbeiter mit Daten in diesem Monat (nicht nur die
    mit Abweichungen) den vollen, editierten Monatsplan - Basis für den
    Kalender-Tab und den Excel-/PDF-Export."""
    _rows, gruppen_ids, gruppen_namen, up_gruppen, sm_gruppen, _id_zu_gruppe = _gruppen_fuer_monat(jahr, monat)

    ergebnis: list[MitarbeiterMonatsplan] = []
    for gruppe in sorted(up_gruppen | sm_gruppen):
        alle_ids = sorted(gruppen_ids[gruppe])
        anzeige_name = max(
            sorted(gruppen_namen[gruppe]), key=lambda n: (_namens_vollstaendigkeit(n), len(n))
        )
        ergebnis.append(MitarbeiterMonatsplan(
            mitarbeiter_id=min(alle_ids), name=anzeige_name, mitarbeiter_ids=alle_ids,
            tage=monatsplan_fuer_mitarbeiter(jahr, monat, alle_ids),
        ))

    ergebnis.sort(key=lambda m: m.name.lower())
    return ergebnis


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


def get_manuelle_zuordnungen() -> list[tuple[int, int]]:
    """Alle vom Nutzer manuell bestätigten Mitarbeiter-Verknüpfungen."""
    con = get_connection()
    try:
        rows = con.execute(
            "SELECT mitarbeiter_id_a, mitarbeiter_id_b FROM abgleich_manuelle_zuordnung"
        ).fetchall()
        return [(r["mitarbeiter_id_a"], r["mitarbeiter_id_b"]) for r in rows]
    finally:
        con.close()


def manuell_zusammenfuehren(mitarbeiter_id_a: int, mitarbeiter_id_b: int) -> None:
    """Merkt zwei Mitarbeiter-Identitäten dauerhaft als dieselbe Person, auch
    wenn die automatische Namenszuordnung sie nicht selbst verbunden hat."""
    if mitarbeiter_id_a == mitarbeiter_id_b:
        return
    a, b = sorted((mitarbeiter_id_a, mitarbeiter_id_b))
    con = get_connection()
    try:
        con.execute(
            "INSERT OR IGNORE INTO abgleich_manuelle_zuordnung (mitarbeiter_id_a, mitarbeiter_id_b, erstellt_am) "
            "VALUES (?, ?, ?)",
            (a, b, jetzt()),
        )
        con.commit()
    finally:
        con.close()


def manuelle_zuordnung_aufheben(mitarbeiter_id_a: int, mitarbeiter_id_b: int) -> None:
    a, b = sorted((mitarbeiter_id_a, mitarbeiter_id_b))
    con = get_connection()
    try:
        con.execute(
            "DELETE FROM abgleich_manuelle_zuordnung WHERE mitarbeiter_id_a = ? AND mitarbeiter_id_b = ?",
            (a, b),
        )
        con.commit()
    finally:
        con.close()


def get_manuelle_trennungen() -> list[tuple[int, int]]:
    """Alle vom Nutzer erzwungenen Trennungen (Namen, die NIE zusammengeführt werden sollen)."""
    con = get_connection()
    try:
        rows = con.execute(
            "SELECT mitarbeiter_id_a, mitarbeiter_id_b FROM abgleich_manuelle_trennung"
        ).fetchall()
        return [(r["mitarbeiter_id_a"], r["mitarbeiter_id_b"]) for r in rows]
    finally:
        con.close()


def manuell_trennen(mitarbeiter_id_a: int, mitarbeiter_id_b: int) -> None:
    """Erzwingt, dass zwei Mitarbeiter-Identitäten NIE als dieselbe Person gelten
    - hebt bei Bedarf eine bestehende manuelle Zuordnung zwischen ihnen auf und
    trennt sie auch, falls die automatische Erkennung sie sonst zusammenführen würde."""
    if mitarbeiter_id_a == mitarbeiter_id_b:
        return
    a, b = sorted((mitarbeiter_id_a, mitarbeiter_id_b))
    con = get_connection()
    try:
        con.execute(
            "DELETE FROM abgleich_manuelle_zuordnung WHERE mitarbeiter_id_a = ? AND mitarbeiter_id_b = ?",
            (a, b),
        )
        con.execute(
            "INSERT OR IGNORE INTO abgleich_manuelle_trennung (mitarbeiter_id_a, mitarbeiter_id_b, erstellt_am) "
            "VALUES (?, ?, ?)",
            (a, b, jetzt()),
        )
        con.commit()
    finally:
        con.close()


def manuelle_trennung_aufheben(mitarbeiter_id_a: int, mitarbeiter_id_b: int) -> None:
    a, b = sorted((mitarbeiter_id_a, mitarbeiter_id_b))
    con = get_connection()
    try:
        con.execute(
            "DELETE FROM abgleich_manuelle_trennung WHERE mitarbeiter_id_a = ? AND mitarbeiter_id_b = ?",
            (a, b),
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
