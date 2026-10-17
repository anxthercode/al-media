from __future__ import annotations

from al_media.config import app_root


def stylesheet(theme: str) -> str:
    dark = theme == "dark"
    bg, surface, raised, text, muted, border, accent, tint = (
        ("#14171c", "#1c2027", "#252b34", "#edf1f5", "#9ba7b6", "#333c48", "#5cdbca", "#203d3c") if dark else
        ("#f3f5f8", "#ffffff", "#eef2f6", "#202a35", "#667485", "#dce2e9", "#087f72", "#e0f4ef")
    )
    check = (app_root() / "assets" / "check.svg").as_posix()
    down = (app_root() / "assets" / "chevron-down.svg").as_posix()
    up = (app_root() / "assets" / "chevron-up.svg").as_posix()
    return f"""
        QWidget {{ color: {text}; font-family: 'Segoe UI'; font-size: 13px; }}
        QMainWindow, QWidget#shell, QWidget#page, QWidget#scrollBody {{ background: {bg}; }}
        QLabel, QCheckBox, QScrollArea, QStackedWidget {{ background: transparent; border: none; }}
        QLabel#muted {{ color: {muted}; }}
        QLabel#pageTitle {{ font-size: 25px; font-weight: 600; }}
        QLabel#sectionTitle {{ font-size: 15px; font-weight: 600; }}
        QLabel#cardTitle {{ font-size: 14px; font-weight: 600; }}
        QLabel#brand {{ font-size: 16px; font-weight: 700; color: {accent}; }}
        QLabel#badge {{ color: {accent}; background: {tint}; border-radius: 5px; padding: 4px 8px; }}
        QFrame#sidebar, QFrame#topbar {{ background: {surface}; border: none; }}
        QFrame#sidebar {{ border-right: 1px solid {border}; }}
        QFrame#topbar {{ border-bottom: 1px solid {border}; }}
        QFrame#card, QFrame#panel {{ background: {surface}; border: 1px solid {border}; border-radius: 10px; }}
        QLabel#thumbnail {{ background: {raised}; color: {muted}; border-radius: 6px; font-size: 24px; }}
        QListWidget {{ background: {surface}; border: 1px solid {border}; border-radius: 8px; outline: none; }}
        QListWidget#navigation {{ background: transparent; border: none; padding: 0; }}
        QListWidget::item {{ padding: 12px; border-radius: 6px; }}
        QListWidget::item:hover {{ background: {raised}; }}
        QListWidget::item:selected {{ color: {accent}; background: {tint}; }}
        QLineEdit, QTextEdit, QComboBox, QSpinBox {{ background: {raised}; border: 1px solid {border}; border-radius: 6px; padding: 7px 10px; selection-background-color: {accent}; selection-color: {bg}; }}
        QComboBox {{ padding-right: 26px; min-height: 18px; }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
        QComboBox::down-arrow {{ image: url({down}); width: 14px; height: 14px; }}
        QSpinBox {{ padding-right: 24px; }}
        QSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 24px; border: none; }}
        QSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 24px; border: none; }}
        QSpinBox::up-arrow {{ image: url({up}); width: 14px; height: 14px; }}
        QSpinBox::down-arrow {{ image: url({down}); width: 14px; height: 14px; }}
        QComboBox QAbstractItemView {{ background: {surface}; color: {text}; selection-background-color: {tint}; selection-color: {accent}; border: 1px solid {border}; padding: 4px; }}
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {accent}; }}
        QPushButton {{ background: {raised}; border: 1px solid {border}; border-radius: 6px; padding: 7px 12px; min-height: 18px; }}
        QPushButton:hover {{ background: {tint}; border-color: {accent}; }}
        QPushButton:focus {{ border-color: {accent}; }}
        QPushButton:disabled, QComboBox:disabled {{ color: {muted}; background: {surface}; }}
        QPushButton#primary {{ background: {accent}; color: {'#102522' if dark else '#ffffff'}; border: 1px solid {accent}; font-weight: 600; }}
        QPushButton#primary:disabled {{ background: {raised}; color: {muted}; border-color: {border}; }}
        QPushButton#quiet {{ background: transparent; }}
        QCheckBox {{ spacing: 9px; padding: 5px 0; }}
        QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {muted}; border-radius: 4px; background: {raised}; }}
        QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: url({check}); }}
        QProgressBar {{ background: {border}; border: none; border-radius: 3px; }}
        QProgressBar::chunk {{ background: {accent}; border-radius: 3px; }}
        QScrollBar:vertical {{ width: 10px; background: transparent; margin: 2px; }}
        QScrollBar::handle:vertical {{ background: {border}; border-radius: 4px; min-height: 28px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QToolTip {{ background: {surface}; color: {text}; border: 1px solid {border}; padding: 6px; }}
        QMessageBox, QFileDialog {{ background: {surface}; }}
    """
