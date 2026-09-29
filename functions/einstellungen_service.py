"""
Einfache Key-Value-Einstellungen (z. B. zuletzt gewählter Ordner für die
Tagesdienstplan-Ansicht), gespeichert als JSON-Datei, damit sie
App-Neustarts überdauern.
"""
import json
import os

from config import SETTINGS_PATH


def _laden() -> dict:
    if not os.path.isfile(SETTINGS_PATH):
        return {}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def get_setting(key: str, standard=None):
    return _laden().get(key, standard)


def set_setting(key: str, wert) -> None:
    daten = _laden()
    daten[key] = wert
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
