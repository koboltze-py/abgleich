"""
Parser für Stärkemeldung-Word-Dokumente (.docx).

Erkennt Kategorien (Schichtleiter, Disposition, Behindertenbetreuer, ...),
Zeitbereiche und Mitarbeiternamen unabhängig vom genauen Tabellen-Layout.
Funktioniert sowohl mit dem einfachen Export (nur Absätze) als auch mit dem
Dashboard-Export (Text in einer Tabellenzelle).
"""
import re
from dataclasses import dataclass
from datetime import datetime, date, timedelta

from docx import Document

ZEITRAUM_RE = re.compile(
    r"Zeitraum:\s*\t?\s*(\d{1,2}\.\d{1,2}\.\d{4})\s*(?:bis|-|–|—)\s*(\d{1,2}\.\d{1,2}\.\d{4})"
)
# "07:00-19:00\tName1 / Name2"  oder  "07:00 bis 19:00\tName1"  (Tab ODER mehrere Leerzeichen als Trenner)
ZEIT_RE = re.compile(
    r"^(\d{1,2}:\d{2})\s*(?:-|–|—|bis)\s*(\d{1,2}:\d{2})\s*[\t ]+(.+)$"
)
NICHT_KATEGORIE = {"stärkemeldung", "staerkemeldung"}


@dataclass
class DienstEintrag:
    kategorie: str
    name: str
    start_zeit: str   # "HH:MM"
    end_zeit: str      # "HH:MM"
    datum: date        # Start-Datum des Dienstes
    end_datum: date     # End-Datum (Folgetag bei Nachtschicht)
    dauer_minuten: int
    ebene: str | None = None  # nur bei Ursprungsplanung (Excel): Dienstplan/Abweichung/Arbeitszeit


@dataclass
class ParseErgebnis:
    dateipfad: str
    von_datum: date | None
    bis_datum: date | None
    eintraege: list[DienstEintrag]
    fehler: str | None = None


def _iter_alle_absaetze(doc: Document):
    """Liefert alle Absätze in Dokumentreihenfolge - Fließtext + alle Tabellenzellen (inkl. verschachtelt)."""
    for p in doc.paragraphs:
        yield p
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs
                for nested in cell.tables:
                    for nrow in nested.rows:
                        for ncell in nrow.cells:
                            yield from ncell.paragraphs


def _ist_fett(para) -> bool:
    runs_mit_text = [r for r in para.runs if r.text.strip()]
    if not runs_mit_text:
        return False
    return all(bool(r.bold) for r in runs_mit_text)


def _parse_zeit(zeit_str: str):
    stunde, minute = zeit_str.split(":")
    return int(stunde), int(minute)


def parse_datei(dateipfad: str) -> ParseErgebnis:
    """Liest eine Stärkemeldung-.docx-Datei und liefert alle Dienst-Einträge."""
    try:
        doc = Document(dateipfad)
    except Exception as exc:
        return ParseErgebnis(dateipfad, None, None, [], fehler=f"Datei konnte nicht geöffnet werden: {exc}")

    von_datum: date | None = None
    bis_datum: date | None = None
    kategorie_aktuell: str | None = None
    eintraege: list[DienstEintrag] = []

    for para in _iter_alle_absaetze(doc):
        text = para.text.strip()
        if not text:
            continue

        if von_datum is None:
            m = ZEITRAUM_RE.search(text)
            if m:
                von_datum = datetime.strptime(m.group(1), "%d.%m.%Y").date()
                bis_datum = datetime.strptime(m.group(2), "%d.%m.%Y").date()
                continue

        m = ZEIT_RE.match(text)
        if m:
            if von_datum is None:
                continue
            start_str, end_str, rest = m.groups()
            namen = [n.strip() for n in re.split(r"/", rest) if n.strip()]
            try:
                sh, sm = _parse_zeit(start_str)
                eh, em = _parse_zeit(end_str)
            except ValueError:
                continue
            start_norm = f"{sh:02d}:{sm:02d}"
            end_norm = f"{eh:02d}:{em:02d}"
            end_datum = von_datum + timedelta(days=1) if (eh, em) <= (sh, sm) else von_datum
            start_dt = datetime.combine(von_datum, datetime.min.time()).replace(hour=sh, minute=sm)
            end_dt = datetime.combine(end_datum, datetime.min.time()).replace(hour=eh, minute=em)
            dauer = int((end_dt - start_dt).total_seconds() // 60)
            kat = kategorie_aktuell or "Sonstige"
            for name in namen:
                eintraege.append(DienstEintrag(
                    kategorie=kat, name=name,
                    start_zeit=start_norm, end_zeit=end_norm,
                    datum=von_datum, end_datum=end_datum, dauer_minuten=dauer,
                ))
            continue

        # Möglicher Kategorie-Header: fett, kein Zeitmuster, keine Ziffern
        if _ist_fett(para) and not any(ch.isdigit() for ch in text) and text.lower() not in NICHT_KATEGORIE:
            kategorie_aktuell = text

    if von_datum is None:
        return ParseErgebnis(dateipfad, None, None, [], fehler="Kein Zeitraum gefunden (Dokument unbekanntes Format)")

    return ParseErgebnis(dateipfad, von_datum, bis_datum, eintraege)
