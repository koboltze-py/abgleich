# NeSk Abgleich – DRK Flughafen Köln

Desktop-Anwendung (PySide6, SAP-Fiori-Design wie Nesk3) zum Einlesen der
Stärkemeldungs-Word-Dokumente und zur Erstellung einer filterbaren
Monatsübersicht der Mitarbeiter-Dienstzeiten.

## Funktionen

- **Import**: Mehrere `.docx`-Stärkemeldungen (einzeln oder ganzer Ordner)
  einlesen. Erkennt automatisch Kategorien (Schichtleiter, Disposition,
  Behindertenbetreuer), Zeiten und Mitarbeiternamen – unabhängig vom
  genauen Tabellen-Layout des Dokuments. Nachtschichten (Ende-Zeit ≤
  Start-Zeit) werden automatisch auf den Folgetag gelegt.
- **Monatsübersicht**: Kalenderartige Pivot-Tabelle (Mitarbeiter × Tage)
  sowie eine sortier- und filterbare Liste aller Dienste. Filter nach
  Mitarbeiter (Textsuche), Kategorie und Tagesbereich lassen sich logisch
  kombinieren.
- **Mitarbeiter**: Übersicht mit Dienst-Anzahl und Gesamtstunden. Umbenennen
  und Zusammenführen von Dubletten (z. B. bei unterschiedlicher Schreibweise
  in den Word-Dokumenten).
- **Dashboard**: Kennzahlen auf einen Blick.

## Starten

```powershell
pip install -r requirements.txt
python main.py
```

Die SQLite-Datenbank wird automatisch unter `database/abgleich.db` angelegt.
