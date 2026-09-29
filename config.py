"""
Konfigurationsdatei für NeSk Abgleich
Pfade, App-Einstellungen und Design-Farben (SAP Fiori, wie Nesk3)
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── Datenbank ────────────────────────────────────────────────────────────
_DB_DIR = os.path.join(BASE_DIR, "database")
os.makedirs(_DB_DIR, exist_ok=True)
DB_PATH = os.path.join(_DB_DIR, "abgleich.db")

# ─── Anwendungseinstellungen ──────────────────────────────────────────────
APP_NAME    = "NeSk Abgleich – DRK Flughafen Köln"
APP_VERSION = "1.0.0"

# ─── Einstellungen-Datei (zuletzt genutzter Importordner etc.) ────────────
SETTINGS_PATH = os.path.join(BASE_DIR, "database", "settings.json")

# ─── Datenquellen ──────────────────────────────────────────────────────────
QUELLE_STAERKEMELDUNG   = "Stärkemeldung"
QUELLE_URSPRUNGSPLANUNG = "Ursprungsplanung"

# ─── SAP Fiori Design-Farben (identisch zu Nesk3) ─────────────────────────
FIORI_BLUE        = "#0a6ed1"
FIORI_BLUE_DARK   = "#1565a8"
FIORI_LIGHT_BLUE  = "#eef4fa"
FIORI_TEXT        = "#32363a"
FIORI_BORDER      = "#d9d9d9"
FIORI_SUCCESS     = "#107e3e"
FIORI_WARNING     = "#e9730c"
FIORI_ERROR       = "#bb0000"
FIORI_WHITE       = "#ffffff"
FIORI_SIDEBAR_BG  = "#354a5e"
FIORI_ROW_ALT     = "#f5f6f7"

# Kategorie-Farben für die Übersicht (analog zu Dispo/Betreuer-Kürzeln in Nesk3)
KATEGORIE_FARBEN = {
    "Schichtleiter":        "#0a6ed1",
    "Disposition":          "#107e3e",
    "Behindertenbetreuer":  "#e9730c",
}
KATEGORIE_FARBE_STANDARD = "#5B8AAA"
