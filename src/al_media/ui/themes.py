from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from al_media.config import app_root


def resolved_theme(theme: str) -> str:
    if theme != "system":
        return theme
    app = QApplication.instance()
    return "dark" if app and app.styleHints().colorScheme() == Qt.ColorScheme.Dark else "light"


def palette(theme: str) -> dict[str, str]:
    keys = ("bg", "side", "surface", "input", "text", "muted", "border", "accent", "tint", "on_accent")
    values = (("#14181e", "#191e26", "#1d242e", "#161c24", "#edf3f6", "#a8b7c6", "#34414e", "#64ddcb", "#243d39", "#102c27")
              if resolved_theme(theme) == "dark" else
              ("#f6f8fa", "#eef2f5", "#ffffff", "#f7f9fb", "#182830", "#586b79", "#d8e1e7", "#087e71", "#e1f3ed", "#ffffff"))
    result = dict(zip(keys, values, strict=True))
    result["download"] = "#67d7f0" if resolved_theme(theme) == "dark" else "#087cac"
    result["mode_fill"] = "#263e47" if resolved_theme(theme) == "dark" else "#dfedf2"
    return result


def stylesheet(theme: str) -> str:
    c = palette(theme)
    suffix = "-light" if resolved_theme(theme) == "light" else ""
    down = (app_root() / f"assets/chevron-down{suffix}.svg").as_posix()
    up = (app_root() / f"assets/chevron-up{suffix}.svg").as_posix()
    check = (app_root() / "assets/check.svg").as_posix()
    return f"""
    QWidget {{ color: {c['text']}; font-family: 'Segoe UI'; font-size: 13px; }}
    QMainWindow, QWidget#shell, QWidget#page, QWidget#scrollBody {{ background: {c['bg']}; }}
    QLabel, QCheckBox, QScrollArea, QStackedWidget {{ background: transparent; border: none; }}
    QLabel#muted {{ color: {c['muted']}; }}
    QLabel#pageTitle {{ font-size: 22px; font-weight: 600; }}
    QLabel#sectionTitle {{ font-size: 15px; font-weight: 600; }}
    QLabel#cardTitle {{ font-size: 13px; font-weight: 600; }}
    QLabel#sourceTitle {{ font-size: 17px; font-weight: 600; }}
    QLabel#rowDetails {{ font-size: 12px; color: {c['muted']}; }}
    QLabel#fieldCaption {{ font-size: 12px; color: {c['muted']}; }}
    QLabel#sourceFact {{ font-size: 14px; }}
    QLabel#brand {{ font-size: 17px; font-weight: 600; }}
    QFrame#skeleton {{ background: {c['border']}; border: none; border-radius: 4px; }}
    QLabel#loadingPreview {{ background: {c['input']}; color: {c['muted']}; border-radius: 8px; }}
    QLabel#error {{ color: {'#f4a0a5' if resolved_theme(theme) == 'dark' else '#b62b3c'}; }}
    QFrame#sidebar {{ background: {c['side']}; border: none; border-right: 1px solid {c['border']}; }}
    QFrame#pageHeader, QFrame#brandHeader {{ border: none; border-bottom: 1px solid {c['border']}; }}
    QFrame#brandHeader {{ background: {c['side']}; }}
    QFrame#panel, QFrame#card, QFrame#resource {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px; }}
    QFrame#card[selected="true"] {{ border-color: {c['accent']}; }}
    QFrame#separator {{ background: {c['border']}; border: none; min-height: 1px; max-height: 1px; }}
    QPushButton, QToolButton {{ background: {c['input']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 5px 10px; min-height: 20px; }}
    QPushButton:hover, QToolButton:hover {{ border-color: {c['accent']}; background: {c['tint']}; }}
    QPushButton:focus, QToolButton:focus {{ border-color: {c['accent']}; }}
    QPushButton:disabled, QComboBox:disabled {{ color: {c['muted']}; background: {c['surface']}; }}
    QPushButton#primary {{ background: {c['accent']}; color: {c['on_accent']}; font-weight: 600; border-color: {c['accent']}; }}
    QPushButton#primary:disabled {{ color: {c['muted']}; background: {c['input']}; border-color: {c['border']}; }}
    QPushButton#downloadPrimary {{ background: {'#67d7f0' if resolved_theme(theme) == 'dark' else '#087cac'}; color: {c['on_accent']}; border-color: transparent;
        font-size: 14px; font-weight: 600; padding: 6px 24px; min-height: 26px; }}
    QPushButton#downloadPrimary:hover {{ background: {'#8be7f9' if resolved_theme(theme) == 'dark' else '#096b93'}; }}
    QPushButton#downloadPrimary:pressed {{ background: {'#4dbbd4' if resolved_theme(theme) == 'dark' else '#075779'}; }}
    QPushButton#downloadPrimary:focus {{ border: 2px solid {c['text']}; padding: 5px 23px; }}
    QPushButton#downloadPrimary:disabled {{ color: {c['muted']}; background: {c['input']}; border: 1px solid {c['border']}; }}
    QPushButton#nav {{ text-align: left; background: transparent; border: 1px solid transparent; padding: 8px 12px; color: {c['muted']}; }}
    QPushButton#nav:checked, QPushButton#mode:checked {{ color: {c['accent']}; background: {c['tint']}; border: 1px solid {c['border']}; }}
    QPushButton#nav:hover, QPushButton#mode:hover {{ background: {c['tint']}; }}
    QPushButton#quiet, QToolButton {{ background: transparent; border-color: transparent; }}
    QPushButton#rowAction {{ padding: 4px; background: transparent; border-color: transparent; min-height: 18px; }}
    QPushButton#rowAction:hover {{ background: {c['tint']}; border-color: {c['border']}; }}
    QPushButton#mode {{ background: {c['input']}; padding: 6px 10px; border-color: transparent; }}
    QFrame#modeSwitch {{ background: {c['input']}; border: 1px solid {c['border']}; border-radius: 11px; }}
    QFrame#modeHighlight {{ background: {c['mode_fill']}; border: none; border-radius: 7px; }}
    QPushButton#modeSegment {{ background: transparent; border: none; border-radius: 7px; padding: 4px 12px; font-size: 14px; font-weight: 600; color: {c['muted']}; }}
    QPushButton#modeSegment:checked {{ color: {c['download']}; }}
    QPushButton#modeSegment:hover {{ color: {c['text']}; }}
    QPushButton#disclosure {{ text-align: left; padding: 5px 36px 5px 10px; }}
    QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: {c['input']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 5px 10px;
        selection-background-color: {c['accent']}; selection-color: {c['on_accent']}; }}
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{ border-color: {c['accent']}; }}
    QComboBox, QSpinBox, QDoubleSpinBox {{ min-height: 20px; }}
    QComboBox {{ padding-right: 42px; }}
    QComboBox::drop-down {{ subcontrol-origin: border; subcontrol-position: top right; width: 40px; border: none; }}
    QComboBox::down-arrow {{ image: url({down}); width: 14px; height: 14px; }}
    QSpinBox::up-button, QSpinBox::down-button {{ subcontrol-origin: border; width: 26px; border: none; background: transparent; }}
    QSpinBox::up-button {{ subcontrol-position: top right; }}
    QSpinBox::down-button {{ subcontrol-position: bottom right; }}
    QSpinBox::up-arrow {{ image: url({up}); width: 12px; height: 12px; }}
    QSpinBox::down-arrow {{ image: url({down}); width: 12px; height: 12px; }}
    QComboBox QAbstractItemView, QListWidget {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; selection-background-color: {c['tint']}; selection-color: {c['accent']}; outline: none; }}
    QComboBox QAbstractItemView::item {{ min-height: 26px; padding: 4px 8px; border: none; }}
    QComboBox QAbstractItemView::item:selected {{ background: {c['tint']}; color: {c['accent']}; }}
    QMenu {{ background: {c['surface']}; border: 1px solid {c['border']}; padding: 4px; }}
    QMenu::item {{ padding: 7px 18px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {c['tint']}; color: {c['accent']}; }}
    QListWidget::item {{ padding: 10px; }}
    QLabel#thumbnail {{ background: {c['input']}; border-radius: 7px; }}
    QProgressBar {{ background: {c['border']}; border: none; border-radius: 3px; }}
    QProgressBar::chunk {{ background: {c['accent']}; border-radius: 3px; }}
    QCheckBox {{ spacing: 10px; padding: 4px 0; }}
    QCheckBox#clipToggle {{ padding: 0; }}
    QCheckBox::indicator {{ width: 17px; height: 17px; border: 1px solid {c['muted']}; border-radius: 4px; background: {c['input']}; }}
    QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; image: url({check}); }}
    QScrollArea {{ border: none; }}
    QScrollBar:vertical {{ width: 10px; background: transparent; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 4px; min-height: 28px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QDialog, QMessageBox, QFileDialog {{ background: {c['bg']}; }}
    QToolTip {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 6px; }}
    """
