import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "../components"

Item {
    id: page
    required property var ui
    readonly property var composer: ui.composer
    readonly property var composerState: composer.state
    property real savedScroll: 0
    function focusUrl() { jobs.headerItem.urlField.forceActiveFocus(); jobs.headerItem.urlField.selectAll(); }
    function focusReturn() { jobs.headerItem.folderTrigger.forceActiveFocus(); }
    objectName: "downloadsPage"
    ListView {
        id: jobs
        acceptedButtons: Qt.NoButton
        objectName: "downloadsScroll"
        anchors.fill: parent
        anchors.leftMargin: ui.pagePadding
        anchors.rightMargin: ui.pagePadding
        topMargin: ui.height <= 760 ? 12 : ui.width >= 1700 ? 24 : 20
        bottomMargin: 32
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        reuseItems: true
        currentIndex: -1
        keyNavigationEnabled: false
        activeFocusOnTab: false
        model: ui.queue
        ScrollBar.vertical: UiScrollBar { width: 8; policy: ScrollBar.AsNeeded }
        header: Column {
            property alias urlField: url
            property alias folderTrigger: folderButton
            property alias rangeItem: rangeEditor
            property alias cropItem: crop
            width: jobs.width - 10
            spacing: 0
            Column {
                id: composerColumn
                width: Math.min(1240, parent.width)
                spacing: 0
                UiText { text: ui.t("link"); font.pixelSize: 12; color: Theme.muted; bottomPadding: 6 }
                UiField {
                    id: url
                    objectName: "sourceUrl"
                    width: parent.width
                    leftPadding: 42
                    rightPadding: 44
                    text: page.composerState.url
                    placeholderText: ui.t("link_placeholder")
                    Accessible.name: ui.t("link")
                    onTextEdited: composer.setUrl(text)
                    onAccepted: composer.analyze()
                    Keys.onPressed: event => {
                        if (event.matches(StandardKey.Paste)) { ui.services.pasteSource(); event.accepted = true; }
                    }
                    UiIcon { name: "link"; x: 14; width: 18; height: 18; anchors.verticalCenter: parent.verticalCenter; tint: Theme.quiet }
                    UiButton { objectName: "clearUrl"; anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter; width: 36; ghost: true; compact: true; iconName: "close"; tip: ui.t("clear_link"); visible: url.text.length > 0; onClicked: composer.setUrl("") }
                    TapHandler { acceptedButtons: Qt.RightButton; onTapped: urlMenu.popup() }
                    Menu {
                        id: urlMenu
                        MenuItem { text: ui.t("paste"); onTriggered: ui.services.pasteSource() }
                        MenuItem { text: ui.t("clear_link"); onTriggered: composer.setUrl("") }
                    }
                }
                Row {
                    width: parent.width
                    height: 28
                    spacing: 8
                    UiText { text: page.composerState.error ? ui.t(page.composerState.error) : ""; color: Theme.error; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
                    UiButton { text: ui.t("retry"); visible: page.composerState.phase === "error"; ghost: true; compact: true; height: 24; anchors.verticalCenter: parent.verticalCenter; onClicked: composer.analyze() }
                }
                Item {
                    id: workspace
                    objectName: "workbench"
                    width: parent.width
                    readonly property bool ready: page.composerState.phase === "ready"
                    readonly property real imageWidth: ui.compact ? 448 : 520
                    readonly property real configWidth: Math.min(560, width - imageWidth - (ui.compact ? 24 : 40))
                    height: ready ? Math.max(configuration.height, preview.height) : ui.queue.count > 0 ? 260 : Math.max(280, Math.min(440, jobs.height - 140))
                    Column {
                        id: empty
                        visible: !workspace.ready
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: Math.max(32, (workspace.height - height) * 0.42)
                        width: Math.min(520, parent.width)
                        spacing: 12
                        UiSpinner { objectName: "analysisSpinner"; running: page.composerState.phase === "loading"; anchors.horizontalCenter: parent.horizontalCenter; Accessible.name: ui.t("analyzing") }
                        UiText { objectName: "composerHeading"; width: parent.width; horizontalAlignment: Text.AlignHCenter; text: ui.t(page.composerState.phase === "loading" ? "analyzing" : page.composerState.phase === "batch" ? "batch" : page.composerState.phase === "error" ? "analysis_failed" : "start_link"); font.pixelSize: 24; font.weight: Font.DemiBold }
                        UiText { objectName: "composerHelp"; width: parent.width; horizontalAlignment: Text.AlignHCenter; text: ui.t(page.composerState.phase === "loading" ? "analyzing_help" : page.composerState.phase === "batch" ? "batch_help" : page.composerState.phase === "error" ? "analysis_failed_help" : "start_help"); color: Theme.muted }
                        UiButton { visible: page.composerState.phase === "batch"; anchors.horizontalCenter: parent.horizontalCenter; width: Math.min(320, parent.width); text: ui.t("download_now"); primary: true; iconName: "download"; onClicked: composer.download() }
                    }
                    Column {
                        id: configuration
                        objectName: "configuration"
                        visible: workspace.ready
                        width: workspace.configWidth
                        spacing: 0
                        UiText { objectName: "sourceTitle"; width: parent.width; text: page.composerState.title; font.pixelSize: ui.compact ? 22 : 24; font.weight: Font.DemiBold; font.letterSpacing: -0.3; lineHeight: font.pixelSize * 1.3 }
                        UiText { width: parent.width; text: [page.composerState.author, page.composerState.source, page.composerState.duration].filter(s => s.length > 0).join("  ·  "); color: Theme.muted; topPadding: 6; bottomPadding: 16 }
                        Rectangle {
                            id: modes
                            width: parent.width
                            height: 48
                            radius: 6
                            color: Theme.surface
                            border.color: Theme.field
                            visible: !page.composerState.isPlaylist
                            Rectangle {
                                width: (parent.width - 8) / 2
                                height: 40
                                x: page.composerState.mode === "video" ? 4 : 4 + width
                                y: 4
                                radius: 5
                                color: Theme.surface3
                                border.color: Theme.field
                                Behavior on x { NumberAnimation { duration: Theme.motion; easing.type: Easing.InOutCubic } }
                            }
                            Row {
                                anchors.fill: parent
                                anchors.margins: 4
                                UiButton { objectName: "videoMode"; width: parent.width / 2; height: 40; ghost: true; text: ui.t("video_mode"); enabled: page.composerState.videoAvailable; font.weight: page.composerState.mode === "video" ? Font.DemiBold : Font.Normal; onClicked: composer.setMode("video") }
                                UiButton { objectName: "audioMode"; width: parent.width / 2; height: 40; ghost: true; text: ui.t("audio_mode"); enabled: page.composerState.audioAvailable; font.weight: page.composerState.mode === "audio" ? Font.DemiBold : Font.Normal; onClicked: composer.setMode("audio") }
                            }
                        }
                        Item { width: 1; height: 12 }
                        Item {
                            id: parameterSlot
                            objectName: "parameterSlot"
                            width: parent.width
                            height: 112
                            Column {
                                width: parent.width
                                spacing: 6
                                visible: !page.composerState.rangeOpen
                                UiText { text: ui.t(page.composerState.mode === "video" ? "video_quality" : "audio_quality"); color: Theme.muted; font.pixelSize: 12 }
                                RowLayout {
                                    width: parent.width
                                    spacing: 12
                                    UiCombo {
                                        objectName: "audioFormat"
                                        visible: page.composerState.mode === "audio"
                                        Layout.fillWidth: page.composerState.audioFormat !== "mp3"
                                        Layout.preferredWidth: Math.max(125, parameterSlot.width * 0.38)
                                        model: page.composerState.audioFormats
                                        value: page.composerState.audioFormat
                                        onChosen: value => composer.setAudioFormat(value)
                                    }
                                    UiCombo {
                                        objectName: "qualityPicker"
                                        visible: page.composerState.mode === "video" || page.composerState.audioFormat === "mp3"
                                        Layout.fillWidth: true
                                        model: page.composerState.options
                                        value: page.composerState.selection
                                        Accessible.name: ui.t(page.composerState.mode === "video" ? "video_quality" : "bitrate")
                                        onChosen: value => composer.select(value)
                                    }
                                }
                            }
                            Column {
                                id: rangeEditor
                                objectName: "rangeEditor"
                                visible: page.composerState.rangeOpen
                                width: parent.width
                                spacing: 6
                                RowLayout {
                                    width: parent.width
                                    spacing: 12
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        Layout.preferredWidth: 1
                                        Layout.minimumWidth: 0
                                        spacing: 4
                                        UiText { text: ui.t("from"); color: Theme.muted; font.pixelSize: 12 }
                                        UiTimeField { objectName: "rangeStart"; Layout.fillWidth: true; text: page.composerState.rangeStart; placeholderText: "00:00:00"; Accessible.name: ui.t("from"); units: [ui.t("time_hours"), ui.t("time_minutes"), ui.t("time_seconds")]; hasError: page.composerState.rangeError !== ""; onEdited: value => composer.editRange("start", value) }
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        Layout.preferredWidth: 1
                                        Layout.minimumWidth: 0
                                        spacing: 4
                                        UiText { text: ui.t("to"); color: Theme.muted; font.pixelSize: 12 }
                                        UiTimeField { objectName: "rangeEnd"; Layout.fillWidth: true; text: page.composerState.rangeEnd; placeholderText: page.composerState.durationHint; Accessible.name: ui.t("to"); units: [ui.t("time_hours"), ui.t("time_minutes"), ui.t("time_seconds")]; hasError: page.composerState.rangeError !== ""; onEdited: value => composer.editRange("end", value) }
                                    }
                                }
                                RowLayout {
                                    width: parent.width
                                    spacing: 8
                                    UiText { text: page.composerState.rangeError ? ui.t(page.composerState.rangeError) : ui.t("clip"); color: page.composerState.rangeError ? Theme.error : Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; maximumLineCount: 2; elide: Text.ElideRight }
                                    UiButton { objectName: "resetRange"; text: ui.t("reset"); onClicked: composer.resetRange() }
                                    UiButton { objectName: "applyRange"; text: ui.t("apply"); onClicked: composer.applyRange() }
                                    UiButton { width: 28; ghost: true; compact: true; iconName: "close"; tip: ui.t("close"); onClicked: composer.closeRange() }
                                }
                            }
                        }
                        Row {
                            id: extras
                            width: parent.width
                            height: 40
                            spacing: 8
                            leftPadding: (width - crop.width - (more.visible ? more.width + spacing : 0)) / 2
                            UiButton { id: crop; objectName: "cropButton"; height: 36; iconName: "trim"; iconSize: 16; horizontalPadding: 10; text: page.composerState.hasRange ? page.composerState.rangeLabel : ui.t("crop"); enabled: !page.composerState.isPlaylist; onClicked: composer.toggleRange() }
                            UiButton { id: more; visible: page.composerState.hasExtra; height: 36; iconName: "settings"; tip: ui.t("more_tracks"); width: 36; compact: true; onClicked: tracks.open() }
                        }
                        Item { height: 12; width: 1 }
                        UiButton { objectName: "downloadButton"; width: parent.width; height: 48; primary: true; iconName: "download"; text: ui.t("download_now"); enabled: page.composerState.canDownload && !ui.services.closing; onClicked: composer.download() }
                        RowLayout {
                            width: parent.width
                            height: 30
                            spacing: 8
                            UiText { text: page.composerState.container + " · ≈ " + page.composerState.estimated; font.pixelSize: 12; color: Theme.muted; wrapMode: Text.NoWrap }
                            UiText { text: ui.settings.state.ask_destination ? ui.t("ask_destination") : ui.settings.state.folder; Layout.fillWidth: true; elide: Text.ElideMiddle; wrapMode: Text.NoWrap; font.pixelSize: 12; color: Theme.muted }
                            UiButton { id: folderButton; objectName: "changeFolder"; text: ui.t("change_folder"); ghost: true; compact: true; height: 24; font.pixelSize: 12; onClicked: ui.services.changeFolder() }
                        }
                        UiText { width: parent.width; visible: page.composerState.rangeDirty && !page.composerState.rangeOpen; text: ui.t("range_pending"); color: Theme.warning; font.pixelSize: 12 }
                    }
                    Rectangle {
                        id: preview
                        objectName: "mediaPreview"
                        visible: workspace.ready
                        anchors.right: parent.right
                        width: workspace.imageWidth
                        height: width * 323 / 577
                        radius: 6
                        color: Theme.surface
                        clip: true
                        Image { id: poster; objectName: "previewImage"; anchors.fill: parent; source: ui.media.source; fillMode: Image.PreserveAspectFit; smooth: true; cache: false }
                        UiText { visible: !ui.media.source; anchors.centerIn: parent; text: ui.t("no_preview"); color: Theme.muted; font.pixelSize: 12 }
                    }
                }
            }
            Item { visible: ui.queue.count > 0; width: 1; height: ui.height <= 760 ? 16 : 24 }
            RowLayout {
                objectName: "queueHeading"
                visible: ui.queue.count > 0
                width: parent.width
                height: 36
                UiText { text: ui.t("jobs_files"); font.pixelSize: 16; font.weight: Font.DemiBold; Layout.fillWidth: true }
                UiButton { objectName: "clearCompleted"; visible: ui.queue.completedCount > 0; text: ui.t("clear_list"); ghost: true; compact: true; font.pixelSize: 12; onClicked: ui.services.clearCompleted() }
            }
        }
        delegate: JobRow { width: jobs.width - 10; ui: page.ui }
    }
    TapHandler {
        enabled: page.composerState.rangeOpen
        onTapped: eventPoint => {
            const p = eventPoint.position;
            const editor = jobs.headerItem.rangeItem;
            const trigger = jobs.headerItem.cropItem;
            const r = editor.mapFromItem(page, p.x, p.y);
            const c = trigger.mapFromItem(page, p.x, p.y);
            if (!(r.x >= 0 && r.y >= 0 && r.x <= editor.width && r.y <= editor.height) && !(c.x >= 0 && c.y >= 0 && c.x <= trigger.width && c.y <= trigger.height)) composer.closeRange();
        }
    }
    Dialog {
        id: tracks
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: 480
        modal: true
        padding: 24
        background: Rectangle { color: Theme.surface; radius: 6; border.color: Theme.field }
        contentItem: ColumnLayout {
            spacing: 12
            UiText { text: ui.t("more_tracks"); font.pixelSize: 20; font.weight: Font.DemiBold }
            UiText { text: ui.t("audio_track"); color: Theme.muted; font.pixelSize: 12 }
            UiCombo { Layout.fillWidth: true; model: page.composerState.tracks; value: page.composerState.track; onChosen: value => composer.setExtra("track", value) }
            UiText { text: ui.t("subtitles"); color: Theme.muted; font.pixelSize: 12 }
            UiCombo { Layout.fillWidth: true; model: page.composerState.subtitles; value: page.composerState.subtitle; onChosen: value => composer.setExtra("subtitle", value) }
            UiCombo { Layout.fillWidth: true; visible: page.composerState.subtitle !== ""; model: page.composerState.mode === "video" ? [{value:"sidecar", label:ui.t("sidecar")}, {value:"embedded", label:ui.t("embedded")}] : [{value:"sidecar",label:ui.t("sidecar")}]; value: page.composerState.subtitleMode; onChosen: value => composer.setExtra("subtitleMode", value) }
            UiButton { text: ui.t("close"); Layout.alignment: Qt.AlignRight; onClicked: tracks.close() }
        }
        Overlay.modal: Rectangle { color: "#aa000000" }
    }
}
