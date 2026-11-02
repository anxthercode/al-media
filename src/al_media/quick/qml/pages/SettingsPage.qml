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
    readonly property string folderNotice: prefs.folderError
    property bool choosingRecent: false
    function focusFolder() {
        const folderY = folderGroup.mapToItem(flick.contentItem, 0, 0).y;
        flick.contentY = Math.max(0, Math.min(folderY - 20, flick.contentHeight - flick.height));
        folderField.forceActiveFocus();
    }
    objectName: "settingsPage"
    Connections {
        target: ui.settings
        function onFolderApplied() {
            if (folderField.activeFocus) {
                folderField.focus = false;
                page.forceActiveFocus(Qt.OtherFocusReason);
            }
        }
    }
    TapHandler {
        onTapped: eventPoint => {
            const field = page.Window.window.activeFocusItem;
            if (!field || !(field instanceof TextInput))
                return;
            const p = field.mapFromItem(page, eventPoint.position.x, eventPoint.position.y);
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
        clip: true
        contentWidth: width
        contentHeight: content.implicitHeight + Theme.spaceLarge * 2
        boundsBehavior: Flickable.StopAtBounds
        UiWheelHandler {
            scrollBar: settingsBar
        }
        ScrollBar.vertical: UiScrollBar {
            id: settingsBar
            objectName: "settingsScrollBar"
            parent: page
            edge: true
            scrollTarget: flick
            upText: ui.t("scroll_up")
            downText: ui.t("scroll_down")
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.right: parent.right
            z: 10
        }
        ColumnLayout {
            id: content
            objectName: "settingsContent"
            x: ui.contentInset
            y: Theme.spaceLarge
            width: flick.width - ui.contentInset * 2
            spacing: Theme.spaceLarge
            SettingsGroup {
                objectName: "appearanceSettingsGroup"
                title: ui.t("appearance")
                Layout.fillWidth: true
                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: Theme.spaceSmall
                    Layout.bottomMargin: Theme.spaceSmall
                    spacing: Theme.spaceLarge
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        Layout.minimumWidth: 0
                        spacing: 6
                        UiText {
                            text: ui.t("theme")
                            color: Theme.muted
                            font.pixelSize: 12
                        }
                        UiCombo {
                            objectName: "themePicker"
                            Layout.fillWidth: true
                            model: [
                                {
                                    value: "system",
                                    label: ui.t("system")
                                },
                                {
                                    value: "dark",
                                    label: ui.t("dark")
                                },
                                {
                                    value: "light",
                                    label: ui.t("light")
                                }
                            ]
                            value: page.prefs.theme
                            Accessible.name: ui.t("theme")
                            onChosen: value => ui.settings.setValue("theme", value)
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        Layout.minimumWidth: 0
                        spacing: 6
                        UiText {
                            text: ui.t("language")
                            color: Theme.muted
                            font.pixelSize: 12
                        }
                        UiCombo {
                            objectName: "languagePicker"
                            Layout.fillWidth: true
                            model: [
                                {
                                    value: "ru",
                                    label: "Русский"
                                },
                                {
                                    value: "en",
                                    label: "English"
                                },
                                {
                                    value: "be",
                                    label: "Беларуская"
                                },
                                {
                                    value: "uk",
                                    label: "Українська"
                                }
                            ]
                            value: page.prefs.language
                            Accessible.name: ui.t("language")
                            onChosen: value => ui.settings.setValue("language", value)
                        }
                    }
                }
            }
            SettingsGroup {
                objectName: "downloadSettingsGroup"
                title: ui.t("download_settings")
                Layout.fillWidth: true
                ColumnLayout {
                    id: folderGroup
                    Layout.fillWidth: true
                    spacing: 0
                    SettingRow {
                        label: ui.t("save_folder")
                        Layout.fillWidth: true
                        UiField {
                            id: folderField
                            objectName: "downloadFolder"
                            text: page.prefs.folderDraft
                            rightPadding: 42
                            hasError: page.prefs.folderError.length > 0
                            Accessible.name: ui.t("save_folder")
                            Accessible.description: page.folderNotice ? ui.t(page.folderNotice) : ""
                            Layout.fillWidth: true
                            onTextEdited: ui.settings.editFolder(text)
                            onAccepted: ui.settings.applyFolder()
                            onEditingFinished: {
                                if (!activeFocus && page.prefs.folderDirty && !page.choosingRecent)
                                    ui.settings.applyFolder();
                            }
                            onActiveFocusChanged: {
                                if (activeFocus)
                                    ui.settings.checkFolder();
                            }
                            Keys.onEscapePressed: {
                                ui.settings.resetFolder();
                                folderField.focus = false;
                                page.forceActiveFocus();
                            }
                            UiButton {
                                id: recentButton
                                objectName: "recentFolders"
                                anchors.right: parent.right
                                anchors.rightMargin: 4
                                anchors.verticalCenter: parent.verticalCenter
                                width: 34
                                height: parent.height - 8
                                enabled: page.prefs.recentFolders.length > 0
                                focusPolicy: Qt.NoFocus
                                tip: ui.t("recent_paths")
                                ghost: true
                                iconSize: 16
                                iconName: "chevron"
                                iconRotation: recentMenu.visible ? 180 : 0
                                selected: recentMenu.visible
                                compact: true
                                function openMenu() {
                                    if (recentMenu.visible)
                                        recentMenu.close();
                                    else {
                                        page.choosingRecent = true;
                                        recentMenu.open();
                                    }
                                }
                                onClicked: openMenu()
                                Popup {
                                    id: recentMenu
                                    objectName: "recentFoldersMenu"
                                    parent: recentButton
                                    popupType: Popup.Item
                                    width: folderField.width
                                    implicitHeight: Math.min(288, recentList.contentHeight) + topPadding + bottomPadding
                                    padding: 6
                                    focus: true
                                    onOpened: recentList.forceActiveFocus()
                                    onClosed: Qt.callLater(() => {
                                        page.choosingRecent = false;
                                    })
                                    // Keep the trigger press for its own toggle instead of
                                    // closing on press and reopening on the button release.
                                    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
                                    onAboutToShow: {
                                        const overlay = Overlay.overlay;
                                        const origin = recentButton.mapToItem(overlay, 0, 0);
                                        x = Math.max(8 - origin.x, Math.min(-recentButton.x, overlay.width - 8 - origin.x - width));
                                        y = origin.y + recentButton.height + 10 + implicitHeight > overlay.height - 8 ? -implicitHeight - 10 :
                                                                                                                        recentButton.height + 10;
                                        recentList.currentIndex = 0;
                                        recentList.forceActiveFocus();
                                    }
                                    background: Rectangle {
                                        color: Theme.surface
                                        radius: 8
                                        border.color: Theme.field
                                    }
                                    contentItem: ListView {
                                        id: recentList
                                        objectName: "recentFoldersList"
                                        implicitHeight: Math.min(288, contentHeight)
                                        clip: true
                                        focus: true
                                        acceptedButtons: Qt.NoButton
                                        keyNavigationEnabled: true
                                        model: page.prefs.recentFolders
                                        Keys.onReturnPressed: {
                                            if (currentItem)
                                                currentItem.choose();
                                        }
                                        Keys.onEnterPressed: {
                                            if (currentItem)
                                                currentItem.choose();
                                        }
                                        ScrollIndicator.vertical: ScrollIndicator {}
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
                                            background: Rectangle {
                                                radius: 4
                                                color: recentItem.highlighted ? Theme.tint : "transparent"
                                            }
                                            contentItem: RowLayout {
                                                spacing: 10
                                                UiIcon {
                                                    objectName: "recentFolderIcon-" + recentItem.index
                                                    name: "folder"
                                                    Layout.preferredWidth: 20
                                                    Layout.preferredHeight: 20
                                                    Layout.maximumWidth: 20
                                                    Layout.maximumHeight: 20
                                                    Layout.alignment: Qt.AlignVCenter
                                                    tint: recentItem.highlighted ? Theme.accent : Theme.muted
                                                }
                                                UiText {
                                                    objectName: "recentFolderPath-" + recentItem.index
                                                    text: recentItem.modelData
                                                    Layout.fillWidth: true
                                                    Layout.minimumWidth: 0
                                                    Layout.alignment: Qt.AlignVCenter
                                                    elide: Text.ElideMiddle
                                                    wrapMode: Text.NoWrap
                                                }
                                            }
                                            ToolTip.visible: hovered
                                            ToolTip.delay: 600
                                            ToolTip.text: modelData
                                        }
                                    }
                                }
                            }
                            Keys.onDownPressed: recentButton.openMenu()
                        }
                        UiButton {
                            text: ui.t("browse")
                            implicitHeight: 48
                            onClicked: ui.settings.browse()
                        }
                    }
                    Item {
                        objectName: "folderFeedback"
                        visible: page.folderNotice.length > 0
                        Layout.preferredWidth: Math.min(520, parent.width * 0.48)
                        Layout.alignment: Qt.AlignRight
                        Layout.preferredHeight: folderFeedbackText.implicitHeight + Theme.spaceSmall
                        UiText {
                            id: folderFeedbackText
                            objectName: "folderError"
                            width: parent.width
                            text: page.folderNotice ? ui.t(page.folderNotice) : ""
                            color: page.prefs.folderError ? Theme.error : Theme.warning
                            font.pixelSize: 12
                        }
                    }
                }
                SettingRow {
                    label: ui.t("ask_destination")
                    Layout.fillWidth: true
                    switchRow: true
                    UiSwitch {
                        objectName: "askDestination"
                        checked: page.prefs.ask_destination
                        Accessible.name: ui.t("ask_destination")
                        onToggled: ui.settings.setValue("ask_destination", checked)
                    }
                }
                SettingRow {
                    label: ui.t("concurrency")
                    Layout.fillWidth: true
                    UiField {
                        objectName: "concurrencyField"
                        Layout.preferredWidth: 112
                        text: page.prefs.numberDraft
                        hasError: page.prefs.numberInvalid
                        Accessible.name: ui.t("concurrency")
                        Accessible.description: page.prefs.numberInvalid ? ui.t("concurrency_invalid") : ""
                        inputMethodHints: Qt.ImhDigitsOnly
                        onTextEdited: ui.settings.setConcurrency(text)
                    }
                    Item {
                        Layout.fillWidth: true
                    }
                }
                UiText {
                    objectName: "concurrencyError"
                    Layout.preferredWidth: Math.min(520, parent.width * 0.48)
                    Layout.alignment: Qt.AlignRight
                    text: ui.t("concurrency_invalid")
                    visible: page.prefs.numberInvalid
                    font.pixelSize: 12
                    color: Theme.error
                }
            }
            SettingsGroup {
                objectName: "fileSettingsGroup"
                title: ui.t("file_settings")
                Layout.fillWidth: true
                SettingRow {
                    label: ui.t("name_style")
                    Layout.fillWidth: true
                    UiCombo {
                        objectName: "nameStyle"
                        Layout.fillWidth: true
                        model: [
                            {
                                value: "title",
                                label: ui.t("title_name")
                            },
                            {
                                value: "artist_title",
                                label: ui.t("artist_title")
                            }
                        ]
                        value: page.prefs.name_style
                        Accessible.name: ui.t("name_style")
                        onChosen: value => ui.settings.setValue("name_style", value)
                    }
                }
                SettingRow {
                    label: ui.t("subfolders")
                    Layout.fillWidth: true
                    UiCombo {
                        objectName: "subfolders"
                        Layout.fillWidth: true
                        model: [
                            {
                                value: "none",
                                label: ui.t("none")
                            },
                            {
                                value: "source",
                                label: ui.t("by_source")
                            },
                            {
                                value: "author",
                                label: ui.t("by_author")
                            },
                            {
                                value: "playlist",
                                label: ui.t("by_playlist")
                            }
                        ]
                        value: page.prefs.subfolders
                        Accessible.name: ui.t("subfolders")
                        onChosen: value => ui.settings.setValue("subfolders", value)
                    }
                }
                SettingRow {
                    id: filenameExample
                    objectName: "filenameExample"
                    Layout.fillWidth: true
                    Layout.topMargin: Theme.spaceSmall
                    controlHeight: 64
                    label: ui.t("filename_example")
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: filenameExample.controlHeight
                        color: Theme.surface
                        radius: 6
                        border.color: Theme.border
                        UiText {
                            objectName: "filenamePreview"
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.margins: Theme.spaceMedium
                            anchors.verticalCenter: parent.verticalCenter
                            text: (page.prefs.subfolders === "none" ? "" : page.prefs.subfolders === "source" ? "YouTube\\" : page.prefs.subfolders
                                                                                                                === "author" ? "Artist\\" : "Playlist\\") + (
                                      page.prefs.name_style === "artist_title" ? "Artist — " : "") + ui.t("title_name") + (page.prefs.media_mode === "video"
                                                                                                                           ? ".mkv" : page.prefs.audio_format
                                                                                                                             === "mp3" ? ".mp3" : ".m4a")
                            color: Theme.muted
                            font.family: "Consolas"
                            font.pixelSize: 12
                            wrapMode: Text.WrapAnywhere
                        }
                    }
                }
            }
            SettingsGroup {
                objectName: "audioSettingsGroup"
                headingName: "audioSettingsHeading"
                title: ui.t("audio_files")
                Layout.fillWidth: true
                SettingRow {
                    label: ui.t("music_tags")
                    Layout.fillWidth: true
                    switchRow: true
                    UiSwitch {
                        objectName: "musicTags"
                        checked: page.prefs.music_tags
                        Accessible.name: ui.t("music_tags")
                        onToggled: ui.settings.setValue("music_tags", checked)
                    }
                }
                SettingRow {
                    label: ui.t("music_cover")
                    Layout.fillWidth: true
                    switchRow: true
                    UiSwitch {
                        objectName: "musicCover"
                        checked: page.prefs.music_cover
                        Accessible.name: ui.t("music_cover")
                        onToggled: ui.settings.setValue("music_cover", checked)
                    }
                }
            }
            SettingsGroup {
                objectName: "behaviorSettingsGroup"
                title: ui.t("behavior")
                Layout.fillWidth: true
                SettingRow {
                    label: ui.t("close_to_tray")
                    Layout.fillWidth: true
                    switchRow: true
                    UiSwitch {
                        objectName: "closeToTray"
                        checked: page.prefs.close_to_tray
                        Accessible.name: ui.t("close_to_tray")
                        onToggled: ui.settings.setValue("close_to_tray", checked)
                    }
                }
            }
        }
    }
}
