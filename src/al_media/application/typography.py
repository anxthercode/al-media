from PySide6.QtGui import QFont, QFontDatabase


def load_font():
    """Use the installed Windows UI face with platform text rendering defaults."""
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    if "Segoe UI" in QFontDatabase.families():
        font.setFamily("Segoe UI")
    font.setPixelSize(14)
    font.setWeight(QFont.Weight.Normal)
    font.setStyleStrategy(QFont.StyleStrategy.PreferDefault)
    font.setHintingPreference(QFont.HintingPreference.PreferDefaultHinting)
    return font
