"""
Gemeinsame Qt-Stylesheet-Bausteine im SAP-Fiori-Look (wie Nesk3).
"""
from config import (
    FIORI_BLUE, FIORI_BLUE_DARK, FIORI_LIGHT_BLUE, FIORI_TEXT,
    FIORI_BORDER, FIORI_WHITE, FIORI_ROW_ALT, FIORI_ERROR,
)

APP_FONT_FAMILY = "Segoe UI"

GLOBAL_QSS = f"""
QWidget {{
    font-family: '{APP_FONT_FAMILY}';
    color: {FIORI_TEXT};
}}
QMainWindow, QStackedWidget {{
    background: {FIORI_WHITE};
}}
QToolTip {{
    background: {FIORI_TEXT};
    color: {FIORI_WHITE};
    border: none;
    padding: 4px 6px;
}}
QLineEdit, QComboBox, QDateEdit, QSpinBox {{
    border: 1px solid {FIORI_BORDER};
    border-radius: 4px;
    padding: 4px 6px;
    background: {FIORI_WHITE};
    min-height: 22px;
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus {{
    border: 1px solid {FIORI_BLUE};
}}
QTabWidget::pane {{
    border: 1px solid {FIORI_BORDER};
    top: -1px;
}}
QTabBar::tab {{
    background: {FIORI_LIGHT_BLUE};
    border: 1px solid {FIORI_BORDER};
    padding: 6px 14px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {FIORI_WHITE};
    border-bottom: 2px solid {FIORI_BLUE};
    font-weight: bold;
}}
"""


def button_primary() -> str:
    return f"""
    QPushButton {{
        background: {FIORI_BLUE};
        color: {FIORI_WHITE};
        border: none;
        border-radius: 4px;
        padding: 7px 18px;
        font-weight: bold;
    }}
    QPushButton:hover {{ background: {FIORI_BLUE_DARK}; }}
    QPushButton:disabled {{ background: #9fc2e3; }}
    """


def button_secondary() -> str:
    return f"""
    QPushButton {{
        background: {FIORI_WHITE};
        color: {FIORI_BLUE};
        border: 1px solid {FIORI_BLUE};
        border-radius: 4px;
        padding: 6px 16px;
        font-weight: bold;
    }}
    QPushButton:hover {{ background: {FIORI_LIGHT_BLUE}; }}
    """


def button_danger() -> str:
    return f"""
    QPushButton {{
        background: {FIORI_WHITE};
        color: {FIORI_ERROR};
        border: 1px solid {FIORI_ERROR};
        border-radius: 4px;
        padding: 6px 16px;
        font-weight: bold;
    }}
    QPushButton:hover {{ background: #fdecec; }}
    """


def table_style() -> str:
    return f"""
    QTableView, QTableWidget {{
        background: {FIORI_WHITE};
        alternate-background-color: {FIORI_ROW_ALT};
        gridline-color: {FIORI_BORDER};
        border: 1px solid {FIORI_BORDER};
        selection-background-color: {FIORI_BLUE};
        selection-color: {FIORI_WHITE};
    }}
    QHeaderView::section {{
        background: {FIORI_LIGHT_BLUE};
        color: {FIORI_TEXT};
        font-weight: bold;
        padding: 6px;
        border: none;
        border-right: 1px solid {FIORI_BORDER};
        border-bottom: 1px solid {FIORI_BORDER};
    }}
    """


def card_style() -> str:
    return f"""
    QFrame {{
        background: {FIORI_WHITE};
        border: 1px solid {FIORI_BORDER};
        border-radius: 6px;
    }}
    """
