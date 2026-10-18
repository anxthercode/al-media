from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout

from al_media import APP_FULL_NAME, APP_NAME
from al_media.i18n.desktop import LANGUAGES

from .widgets import BrandMark

SUPPORTED_SITES = (("YouTube", "youtube"), ("Facebook", "facebook"), ("Instagram", "instagram"),
                   ("TikTok", "tiktok"), ("SoundCloud", "soundcloud"), ("X (Twitter)", "x-twitter"))


def separator(layout):
    line = QFrame()
    line.setObjectName("separator")
    layout.addWidget(line)


def settings_page(window):
    page, layout = window._page()
    layout.addWidget(window._label("appearance", "sectionTitle"))
    fields = QGridLayout()
    fields.setHorizontalSpacing(20)
    fields.setVerticalSpacing(8)
    fields.addWidget(window._label("theme"), 0, 0)
    fields.addWidget(window._label("language"), 0, 1)
    window.theme, window.language = QComboBox(), QComboBox()
    for value in ("system", "dark", "light"):
        window.theme.addItem(value, value)
    window.theme.setCurrentIndex(window.theme.findData(window.preferences.theme))
    for label, value in LANGUAGES:
        window.language.addItem(label, value)
    window.language.setCurrentIndex(window.language.findData(window.preferences.language))
    for column, widget in enumerate((window.theme, window.language)):
        widget.setFixedWidth(280)
        fields.addWidget(widget, 1, column, Qt.AlignmentFlag.AlignLeft)
    fields.setColumnStretch(2, 1)
    layout.addLayout(fields)
    separator(layout)
    layout.addWidget(window._label("saving_options", "sectionTitle"))
    layout.addWidget(window._label("path", "muted"))
    path = QHBoxLayout()
    path.setSpacing(12)
    window.path_edit = QLineEdit(window.preferences.folder)
    window.path_edit.setFixedWidth(440)
    window.path_edit.setToolTip(window.preferences.folder)
    window.path_edit.textChanged.connect(window.path_edit.setToolTip)
    window.choose_button = window._button("choose", window._choose_folder, icon="folder")
    path.addWidget(window.path_edit)
    path.addWidget(window.choose_button)
    path.addStretch()
    layout.addLayout(path)
    grid = QGridLayout()
    grid.setHorizontalSpacing(24)
    grid.setVerticalSpacing(12)
    grid.setColumnMinimumWidth(0, 210)
    window.concurrency = QSpinBox()
    window.concurrency.setRange(1, 5)
    window.concurrency.setValue(window.preferences.concurrency)
    window.concurrency.setFixedWidth(90)
    window.name_style, window.subfolders = QComboBox(), QComboBox()
    for value in ("title", "artist_title"):
        window.name_style.addItem(value, value)
    for value in ("none", "source", "author", "playlist"):
        window.subfolders.addItem(value, value)
    window.name_style.setCurrentIndex(window.name_style.findData(window.preferences.name_style))
    window.subfolders.setCurrentIndex(window.subfolders.findData(window.preferences.subfolders))
    for row, (key, widget) in enumerate((("concurrency", window.concurrency), ("name_style", window.name_style), ("subfolders", window.subfolders))):
        grid.addWidget(window._label(key), row, 0)
        widget.setMaximumWidth(320)
        grid.addWidget(widget, row, 1, Qt.AlignmentFlag.AlignLeft)
    grid.setColumnStretch(1, 1)
    layout.addLayout(grid)
    window.music_tags, window.music_cover = QCheckBox(), QCheckBox()
    for widget, key in ((window.music_tags, "music_tags"), (window.music_cover, "music_cover")):
        window.texts.append((widget, key))
        widget.setChecked(getattr(window.preferences, key))
        layout.addWidget(widget)
    separator(layout)
    layout.addWidget(window._label("behavior", "sectionTitle"))
    window.close_to_tray = QCheckBox()
    window.texts.append((window.close_to_tray, "close_to_tray"))
    window.close_to_tray.setChecked(window.preferences.close_to_tray)
    layout.addWidget(window.close_to_tray)
    layout.addStretch()
    window.path_edit.editingFinished.connect(window._save_settings)
    for widget in (window.theme, window.language, window.name_style, window.subfolders):
        widget.currentIndexChanged.connect(window._save_settings)
    window.concurrency.valueChanged.connect(window._save_settings)
    for widget in (window.music_tags, window.music_cover, window.close_to_tray):
        widget.toggled.connect(window._save_settings)
    return page


def about_page(window):
    page, layout = window._page()
    brand = QHBoxLayout()
    brand.setSpacing(18)
    logo = QLabel()
    logo.setFixedSize(64, 64)
    logo.setPixmap(window.windowIcon().pixmap(QSize(64, 64), window.devicePixelRatioF()))
    brand.addWidget(logo, 0, Qt.AlignmentFlag.AlignTop)
    names = QVBoxLayout()
    names.setSpacing(8)
    title = QLabel(f"{APP_NAME} — {APP_FULL_NAME}")
    title.setObjectName("sourceTitle")
    title.setWordWrap(True)
    names.addWidget(title)
    names.addWidget(window._label("product_description", "muted"))
    window.version_label = QLabel()
    window.version_label.setObjectName("muted")
    names.addWidget(window.version_label)
    brand.addLayout(names, 1)
    layout.addLayout(brand)
    layout.addSpacing(12)
    layout.addWidget(window._label("resources", "sectionTitle"))
    grid = QGridLayout()
    grid.setSpacing(12)
    window.site_icons = []
    for index, (name, icon) in enumerate(SUPPORTED_SITES):
        tile = QFrame()
        tile.setObjectName("resource")
        row = QHBoxLayout(tile)
        row.setContentsMargins(16, 16, 16, 16)
        row.setSpacing(14)
        image = BrandMark(icon)
        image.setFixedSize(32, 32)
        window.site_icons.append((image, icon))
        row.addWidget(image)
        label = QLabel(name)
        label.setWordWrap(True)
        row.addWidget(label, 1)
        grid.addWidget(tile, index // 3, index % 3)
    for column in range(3):
        grid.setColumnStretch(column, 1)
    layout.addLayout(grid)
    row = QHBoxLayout()
    row.addWidget(window._label("other_resources", "muted"), 1)
    resources = window._button("full_resources", lambda: QDesktopServices.openUrl(QUrl("https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md")), icon="external")
    resources.setObjectName("quiet")
    row.addWidget(resources)
    layout.addLayout(row)
    layout.addWidget(window._label("availability", "muted"))
    layout.addStretch(1)
    separator(layout)
    author = QLabel("Developed by Vladislav Galkin (anxthercode)")
    author.setObjectName("muted")
    author.setWordWrap(True)
    window.about_author = author
    layout.addWidget(author)
    footer = QHBoxLayout()
    copyright_label = QLabel("© 2026 anxthercode")
    copyright_label.setObjectName("muted")
    footer.addWidget(copyright_label)
    licenses = window._button("licenses", window._show_licenses, icon="external")
    licenses.setObjectName("quiet")
    footer.addWidget(licenses)
    footer.addStretch()
    layout.addLayout(footer)
    return page
