import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Window
import ".."
import "../components"

FocusScope {
    id: page
    required property var ui
    readonly property var prefs: ui.settings.state
    function focusFolder() {
        flick.contentY = Math.max(0, Math.min(folderGroup.y - 20, flick.contentHeight - flick.height));
        folderField.forceActiveFocus();
    }
    objectName: "settingsPage"
    TapHandler {
        onPressedChanged: {
            if (!pressed) return;
            const field = page.Window.window.activeFocusItem;
            if (!field || field === page) return;
            const p = field.mapFromItem(page, point.position.x, point.position.y);
            if (p.x < 0 || p.y < 0 || p.x > field.width || p.y > field.height) {
                field.focus = false;
                page.forceActiveFocus(Qt.MouseFocusReason);
            }
        }
    }
    Flickable {
        id: flick
        objectName: "settingsScroll"
        acceptedButtons: Qt.NoButton
        anchors.fill: parent
        anchors.leftMargin: ui.pagePadding
        anchors.rightMargin: ui.pagePadding
        anchors.topMargin: 20
        anchors.bottomMargin: 24
        clip: true
        contentWidth: width
        contentHeight: content.implicitHeight
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: UiScrollBar { width: 8 }
        ColumnLayout {
            id: content
            width: Math.min(1000, flick.width - 10)
            spacing: 0
            RowLayout {
                Layout.fillWidth: true
                Layout.bottomMargin: 16
                UiText { text: ui.t("appearance"); font.pixelSize: 16; font.weight: Font.DemiBold; Layout.fillWidth: true }
                UiText { text: page.prefs.saved ? ui.t(page.prefs.saved) : ""; color: Theme.quiet; font.pixelSize: 12 }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 24
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.minimumWidth: 0
                    spacing: 6
                    UiText { text: ui.t("theme"); color: Theme.muted; font.pixelSize: 12 }
                    UiCombo { objectName: "themePicker"; Layout.fillWidth: true; model: [{value:"system", label:ui.t("system")}, {value:"dark",label:ui.t("dark")}, {value:"light",label:ui.t("light")}]; value: page.prefs.theme; Accessible.name: ui.t("theme"); onChosen: value => ui.settings.setValue("theme", value) }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.minimumWidth: 0
                    spacing: 6
                    UiText { text: ui.t("language"); color: Theme.muted; font.pixelSize: 12 }
                    UiCombo { objectName: "languagePicker"; Layout.fillWidth: true; model: [{value:"ru",label:"Русский"},{value:"en",label:"English"},{value:"be",label:"Беларуская"},{value:"uk",label:"Українська"}]; value: page.prefs.language; Accessible.name: ui.t("language"); onChosen: value => ui.settings.setValue("language",value) }
                }
            }
            SectionHeading { text: ui.t("saving"); Layout.fillWidth: true; Layout.topMargin: 28; Layout.bottomMargin: 8 }
            ColumnLayout {
                id: folderGroup
                Layout.fillWidth: true
                spacing: 0
                SettingRow {
                    label: ui.t("save_folder")
                    Layout.fillWidth: true
                    UiField { id: folderField; objectName: "downloadFolder"; text: page.prefs.folder; readOnly: true; Accessible.name: ui.t("save_folder"); Layout.fillWidth: true }
                    UiButton { text: ui.t("browse"); implicitHeight: 48; onClicked: ui.settings.browse() }
                }
                UiButton {
                    id: recentButton
                    objectName: "recentFolders"
                    visible: page.prefs.recentAlternatives.length > 0
                    Layout.alignment: Qt.AlignRight
                    text: ui.t("recent")
                    iconName: "chevron"
                    iconRotation: recentMenu.visible ? 180 : 0
                    selected: recentMenu.visible
                    compact: true
                    onClicked: recentMenu.visible ? recentMenu.close() : recentMenu.open()
                    Popup {
                        id: recentMenu
                        objectName: "recentFoldersMenu"
                        parent: recentButton
                        popupType: Popup.Item
                        width: Math.min(440, content.width * 0.48)
                        implicitHeight: recentList.implicitHeight + topPadding + bottomPadding
                        padding: 6
                        focus: true
                        onOpened: recentList.forceActiveFocus()
                        // Keep the trigger press for its own toggle instead of
                        // closing on press and reopening on the button release.
                        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
                        onAboutToShow: {
                            const overlay = Overlay.overlay;
                            const origin = recentButton.mapToItem(overlay, 0, 0);
                            x = Math.max(8 - origin.x, Math.min(recentButton.width - width, overlay.width - 8 - origin.x - width));
                            y = origin.y + recentButton.height + 6 + implicitHeight > overlay.height - 8 ? -implicitHeight - 6 : recentButton.height + 6;
                            recentList.currentIndex = 0;
                            recentList.forceActiveFocus();
                        }
                        background: Rectangle { color: Theme.surface; radius: 8; border.color: Theme.field }
                        contentItem: ListView {
                            id: recentList
                            objectName: "recentFoldersList"
                            implicitHeight: contentHeight
                            clip: true
                            focus: true
                            acceptedButtons: Qt.NoButton
                            keyNavigationEnabled: true
                            model: page.prefs.recentAlternatives
                            Keys.onReturnPressed: recentList.currentItem.choose()
                            Keys.onEnterPressed: recentList.currentItem.choose()
                            delegate: ItemDelegate {
                                id: recentItem
                                required property var modelData
                                required property int index
                                objectName: "recentFolder-" + index
                                width: recentList.width
                                height: 48
                                padding: 12
                                hoverEnabled: true
                                Accessible.name: modelData
                                highlighted: hovered || (recentList.activeFocus && recentList.currentIndex === index)
                                function choose() {
                                    const folder = modelData;
                                    recentMenu.close();
                                    ui.settings.chooseRecent(folder);
                                }
                                onClicked: choose()
                                background: Rectangle { radius: 4; color: recentItem.highlighted ? Theme.tint : "transparent" }
                                contentItem: RowLayout {
                                    spacing: 10
                                    UiIcon { objectName: "recentFolderIcon-" + recentItem.index; name: "folder"; Layout.preferredWidth: 20; Layout.preferredHeight: 20; Layout.maximumWidth: 20; Layout.maximumHeight: 20; Layout.alignment: Qt.AlignVCenter; tint: recentItem.highlighted ? Theme.accent : Theme.muted }
                                    UiText { objectName: "recentFolderPath-" + recentItem.index; text: recentItem.modelData; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.alignment: Qt.AlignVCenter; elide: Text.ElideMiddle; wrapMode: Text.NoWrap }
                                }
                                ToolTip.visible: hovered
                                ToolTip.delay: 600
                                ToolTip.text: modelData
                            }
                        }
                    }
                }
            }
            SettingRow { label: ui.t("ask_destination"); Layout.fillWidth: true; switchRow: true; UiSwitch { objectName: "askDestination"; checked: page.prefs.ask_destination; Accessible.name: ui.t("ask_destination"); onToggled: ui.settings.setValue("ask_destination", checked) } }
            SettingRow {
                label: ui.t("concurrency")
                Layout.fillWidth: true
                UiField { objectName: "concurrencyField"; Layout.preferredWidth: 112; text: page.prefs.numberDraft; hasError: page.prefs.numberInvalid; Accessible.name: ui.t("concurrency"); Accessible.description: page.prefs.numberInvalid ? ui.t("concurrency_invalid") : ""; inputMethodHints: Qt.ImhDigitsOnly; onTextEdited: ui.settings.setConcurrency(text) }
                Item { Layout.fillWidth: true }
            }
            UiText { objectName: "concurrencyError"; Layout.preferredWidth: Math.min(440, content.width * 0.48); Layout.alignment: Qt.AlignRight; text: ui.t("concurrency_invalid"); visible: page.prefs.numberInvalid; font.pixelSize: 12; color: Theme.error }
            SettingRow { label: ui.t("name_style"); Layout.fillWidth: true; UiCombo { objectName: "nameStyle"; Layout.fillWidth: true; model: [{value:"title",label:ui.t("title_name")},{value:"artist_title",label:ui.t("artist_title")}]; value: page.prefs.name_style; Accessible.name: ui.t("name_style"); onChosen: value => ui.settings.setValue("name_style",value) } }
            SettingRow { label: ui.t("subfolders"); Layout.fillWidth: true; UiCombo { objectName: "subfolders"; Layout.fillWidth: true; model: [{value:"none",label:ui.t("none")},{value:"source",label:ui.t("by_source")},{value:"author",label:ui.t("by_author")},{value:"playlist",label:ui.t("by_playlist")}]; value: page.prefs.subfolders; Accessible.name: ui.t("subfolders"); onChosen: value => ui.settings.setValue("subfolders",value) } }
            SettingRow {
                Layout.fillWidth: true
                implicitHeight: 32
                label: ui.t("example")
                UiText {
                    Layout.fillWidth: true
                    text: (page.prefs.subfolders === "none" ? "" : page.prefs.subfolders === "source" ? "YouTube\\" : page.prefs.subfolders === "author" ? "Artist\\" : "Playlist\\") + (page.prefs.name_style === "artist_title" ? "Artist — " : "") + ui.t("title_name") + (page.prefs.media_mode === "video" ? ".mkv" : page.prefs.audio_format === "mp3" ? ".mp3" : ".m4a")
                    color: Theme.quiet
                    font.family: "Consolas"
                    font.pixelSize: 12
                }
            }
            SectionHeading { text: ui.t("audio_files"); Layout.fillWidth: true; Layout.topMargin: 28; Layout.bottomMargin: 8 }
            SettingRow { label: ui.t("music_tags"); Layout.fillWidth: true; switchRow: true; UiSwitch { objectName: "musicTags"; checked: page.prefs.music_tags; Accessible.name: ui.t("music_tags"); onToggled: ui.settings.setValue("music_tags",checked) } }
            SettingRow { label: ui.t("music_cover"); Layout.fillWidth: true; switchRow: true; UiSwitch { objectName: "musicCover"; checked: page.prefs.music_cover; Accessible.name: ui.t("music_cover"); onToggled: ui.settings.setValue("music_cover",checked) } }
            SectionHeading { text: ui.t("behavior"); Layout.fillWidth: true; Layout.topMargin: 28; Layout.bottomMargin: 8 }
            SettingRow { label: ui.t("close_to_tray"); Layout.fillWidth: true; switchRow: true; UiSwitch { objectName: "closeToTray"; checked: page.prefs.close_to_tray; Accessible.name: ui.t("close_to_tray"); onToggled: ui.settings.setValue("close_to_tray",checked) } }
        }
    }
}
