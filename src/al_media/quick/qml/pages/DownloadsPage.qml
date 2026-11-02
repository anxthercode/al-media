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
    function focusUrl() {
        jobs.headerItem.urlField.forceActiveFocus();
        jobs.headerItem.urlField.selectAll();
    }
    function focusReturn() {
        jobs.headerItem.folderTrigger.forceActiveFocus();
    }
    objectName: "downloadsPage"
    ListView {
        id: jobs
        acceptedButtons: Qt.NoButton
        objectName: "downloadsScroll"
        anchors.fill: parent
        topMargin: Theme.spaceLarge
        bottomMargin: 32
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        reuseItems: true
        currentIndex: -1
        keyNavigationEnabled: false
        activeFocusOnTab: false
        model: ui.queue
        UiWheelHandler {
            scrollBar: downloadsBar
        }
        ScrollBar.vertical: UiScrollBar {
            id: downloadsBar
            objectName: "downloadsScrollBar"
            parent: page
            edge: true
            scrollTarget: jobs
            upText: ui.t("scroll_up")
            downText: ui.t("scroll_down")
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.right: parent.right
            z: 10
        }
        header: Item {
            property alias urlField: url
            property alias folderTrigger: folderButton
            property alias rangeItem: rangeEditor
            property alias cropItem: crop
            width: jobs.width
            height: headerContent.implicitHeight
            Column {
                id: headerContent
                objectName: "downloadsContent"
                x: ui.contentInset
                width: jobs.width - ui.contentInset * 2
                spacing: 0
                Column {
                    id: composerColumn
                    width: parent.width
                    spacing: 0
                    UiText {
                        text: ui.t("link")
                        font.pixelSize: 12
                        color: Theme.muted
                        bottomPadding: 6
                    }
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
                            if (event.matches(StandardKey.Paste)) {
                                ui.services.pasteSource();
                                event.accepted = true;
                            }
                        }
                        UiIcon {
                            name: "link"
                            x: 14
                            width: 20
                            height: 20
                            anchors.verticalCenter: parent.verticalCenter
                            tint: url.activeFocus ? Theme.accent : Theme.muted
                        }
                        UiButton {
                            objectName: "clearUrl"
                            anchors.right: parent.right
                            anchors.rightMargin: 6
                            anchors.verticalCenter: parent.verticalCenter
                            width: 36
                            ghost: true
                            compact: true
                            iconName: "close"
                            tip: ui.t("clear_link")
                            visible: url.text.length > 0
                            onClicked: composer.setUrl("")
                        }
                        TapHandler {
                            acceptedButtons: Qt.RightButton
                            onTapped: urlMenu.popup()
                        }
                        Menu {
                            id: urlMenu
                            objectName: "sourceContextMenu"
                            MenuItem {
                                text: ui.t("paste")
                                onTriggered: ui.services.pasteSource()
                            }
                            MenuItem {
                                text: ui.t("clear_link")
                                onTriggered: composer.setUrl("")
                            }
                        }
                    }
                    Row {
                        width: parent.width
                        height: 28
                        spacing: 8
                        UiText {
                            text: page.composerState.error ? ui.t(page.composerState.error) : ""
                            color: Theme.error
                            font.pixelSize: 12
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        UiButton {
                            text: ui.t("retry")
                            visible: page.composerState.phase === "error"
                            ghost: true
                            compact: true
                            height: 24
                            anchors.verticalCenter: parent.verticalCenter
                            onClicked: composer.analyze()
                        }
                    }
                    Item {
                        id: workspace
                        objectName: "workbench"
                        width: parent.width
                        readonly property bool ready: page.composerState.phase === "ready"
                        readonly property real minimumColumnGap: ui.compact ? 24 : 48
                        readonly property real configWidth: Math.min(640, Math.round((width - minimumColumnGap) * 0.52))
                        readonly property real imageWidth: Math.min(592, width - configWidth - minimumColumnGap)
                        readonly property real naturalHeight: Math.max(configuration.height + (page.composerState.isPlaylist ? extras.height : 0), preview.height)
                        property real lastReadyHeight: 0
                        function rememberReadyHeight() {
                            if (ready) lastReadyHeight = naturalHeight;
                        }
                        onNaturalHeightChanged: Qt.callLater(rememberReadyHeight)
                        onReadyChanged: Qt.callLater(rememberReadyHeight)
                        onWidthChanged: {
                            lastReadyHeight = 0;
                            Qt.callLater(rememberReadyHeight);
                        }
                        Component.onCompleted: Qt.callLater(rememberReadyHeight)
                        height: ready ? naturalHeight : Math.max(naturalHeight, lastReadyHeight, empty.implicitHeight + 64,
                                                                ui.queue.count > 0 ? 0 : Math.max(280, Math.min(440, jobs.height - 140)))
                        Item {
                            id: empty
                            objectName: "composerMessage"
                            visible: !workspace.ready
                            anchors.horizontalCenter: parent.horizontalCenter
                            // Anchor the heading independently of the spinner and
                            // actions; keep room for the queue on tall windows.
                            y: Math.round(Math.min(220, Math.max(88, jobs.height / 2 - jobs.topMargin - workspace.y - stateHeading.height / 2)))
                            width: Math.min(parent.width, Math.ceil(["start_link", "analyzing", "playlist_choice", "batch", "analysis_failed"].reduce(
                                (value, key) => Math.max(value, headingMetrics.advanceWidth(ui.t(key)) + 2), 520)))
                            implicitHeight: stateHelp.y + stateHelp.height + 16 + 48
                            height: implicitHeight
                            FontMetrics {
                                id: headingMetrics
                                font: stateHeading.font
                            }
                            UiSpinner {
                                objectName: "analysisSpinner"
                                running: page.composerState.phase === "loading"
                                anchors.horizontalCenter: parent.horizontalCenter
                                anchors.bottom: parent.top
                                anchors.bottomMargin: 20
                                Accessible.name: ui.t("analyzing")
                            }
                            UiText {
                                id: stateHeading
                                objectName: "composerHeading"
                                width: parent.width
                                height: lineHeight
                                wrapMode: Text.NoWrap
                                horizontalAlignment: Text.AlignHCenter
                                text: ui.t(page.composerState.phase === "choice" ? "playlist_choice" : page.composerState.phase === "loading" ? "analyzing" : page.composerState.phase === "batch" ? "batch" : page.composerState.phase === "error" ? "analysis_failed" : "start_link")
                                font.pixelSize: 24
                                font.weight: Font.DemiBold
                            }
                            UiText {
                                id: stateHelp
                                objectName: "composerHelp"
                                y: stateHeading.height + 12
                                width: parent.width
                                height: Math.max(implicitHeight, lineHeight * 2)
                                horizontalAlignment: Text.AlignHCenter
                                text: ui.t(page.composerState.phase === "choice" ? "playlist_choice_help" : page.composerState.phase === "loading" ? "analyzing_help" : page.composerState.phase === "batch" ? "batch_help" : page.composerState.phase === "error" ? "analysis_failed_help" : "start_help")
                                color: Theme.muted
                            }
                            Row {
                                visible: page.composerState.phase === "choice"
                                anchors.horizontalCenter: parent.horizontalCenter
                                y: stateHelp.y + stateHelp.height + 16
                                spacing: 8
                                UiButton {
                                    objectName: "onlyVideo"
                                    height: 40
                                    text: ui.t("only_video")
                                    onClicked: composer.choosePlaylist(false)
                                }
                                UiButton {
                                    objectName: "choosePlaylist"
                                    height: 40
                                    text: ui.t("choose_playlist")
                                    primary: true
                                    onClicked: composer.choosePlaylist(true)
                                }
                            }
                            UiButton {
                                objectName: "downloadBatch"
                                visible: page.composerState.phase === "batch"
                                anchors.horizontalCenter: parent.horizontalCenter
                                y: stateHelp.y + stateHelp.height + 16
                                width: Math.min(320, parent.width)
                                height: 48
                                text: ui.t("download_now")
                                primary: true
                                iconName: "download"
                                onClicked: composer.download()
                            }
                        }
                        Column {
                            id: configuration
                            objectName: "configuration"
                            visible: workspace.ready
                            width: workspace.configWidth
                            spacing: 0
                            UiText {
                                objectName: "sourceTitle"
                                width: parent.width
                                text: page.composerState.title
                                height: Math.max(implicitHeight, lineHeight)
                                font.pixelSize: ui.compact ? 22 : 24
                                font.weight: Font.DemiBold
                                font.letterSpacing: -0.3
                                lineHeight: font.pixelSize * 1.3
                            }
                            UiText {
                                width: parent.width
                                text: [page.composerState.author, page.composerState.source, page.composerState.duration].filter(s => s.length > 0).join("  ·  ")
                                height: Math.max(implicitHeight, lineHeight + topPadding + bottomPadding)
                                color: Theme.muted
                                topPadding: 6
                                bottomPadding: 16
                            }
                            Rectangle {
                                id: modes
                                property string requestedMode: ""
                                readonly property string displayedMode: requestedMode || page.composerState.mode
                                function choose(mode) {
                                    if (mode === displayedMode)
                                        return;
                                    requestedMode = mode;
                                    Qt.callLater(commitMode);
                                }
                                function commitMode() {
                                    composer.setMode(requestedMode);
                                    requestedMode = "";
                                }
                                width: parent.width
                                height: 48
                                radius: 6
                                color: Theme.surface
                                border.color: Theme.field
                                visible: true
                                Rectangle {
                                    objectName: "modeHighlight"
                                    width: (modes.width - 12) / 2
                                    height: 40
                                    x: modes.displayedMode === "video" ? 4 : width + 8
                                    y: 4
                                    radius: 5
                                    color: Theme.surface3
                                    border.color: Theme.field
                                    Behavior on x {
                                        SmoothedAnimation {
                                            duration: Theme.reducedMotion ? 0 : 180
                                            velocity: -1
                                            reversingMode: SmoothedAnimation.Immediate
                                        }
                                    }
                                }
                                Row {
                                    anchors.fill: parent
                                    anchors.margins: 4
                                    spacing: 4
                                    UiButton {
                                        objectName: "videoMode"
                                        width: (parent.width - parent.spacing) / 2
                                        height: 40
                                        segment: true
                                        drawSelection: false
                                        selected: modes.displayedMode === "video"
                                        text: ui.t("video_mode")
                                        enabled: page.composerState.videoAvailable
                                        font.weight: selected ? Font.DemiBold : Font.Normal
                                        onClicked: modes.choose("video")
                                    }
                                    UiButton {
                                        objectName: "audioMode"
                                        width: (parent.width - parent.spacing) / 2
                                        height: 40
                                        segment: true
                                        drawSelection: false
                                        selected: modes.displayedMode === "audio"
                                        text: ui.t("audio_mode")
                                        enabled: page.composerState.audioAvailable
                                        font.weight: selected ? Font.DemiBold : Font.Normal
                                        onClicked: modes.choose("audio")
                                    }
                                }
                            }
                            Item {
                                width: 1
                                height: 12
                            }
                            Item {
                                id: parameterSlot
                                objectName: "parameterSlot"
                                width: parent.width
                                height: 112
                                Column {
                                    width: parent.width
                                    spacing: 6
                                    visible: !page.composerState.rangeOpen
                                    UiText {
                                        text: ui.t(page.composerState.mode === "video" ? "video_quality" : "audio_quality")
                                        color: Theme.muted
                                        font.pixelSize: 12
                                    }
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
                                            UiText {
                                                text: ui.t("from")
                                                color: Theme.muted
                                                font.pixelSize: 12
                                            }
                                            UiTimeField {
                                                objectName: "rangeStart"
                                                Layout.fillWidth: true
                                                text: page.composerState.rangeStart
                                                placeholderText: "00:00:00"
                                                Accessible.name: ui.t("from")
                                                units: [ui.t("time_hours"), ui.t("time_minutes"), ui.t("time_seconds")]
                                                hasError: page.composerState.rangeError !== ""
                                                onEdited: value => composer.editRange("start", value)
                                            }
                                        }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            Layout.preferredWidth: 1
                                            Layout.minimumWidth: 0
                                            spacing: 4
                                            UiText {
                                                text: ui.t("to")
                                                color: Theme.muted
                                                font.pixelSize: 12
                                            }
                                            UiTimeField {
                                                objectName: "rangeEnd"
                                                Layout.fillWidth: true
                                                text: page.composerState.rangeEnd
                                                placeholderText: page.composerState.durationHint
                                                Accessible.name: ui.t("to")
                                                units: [ui.t("time_hours"), ui.t("time_minutes"), ui.t("time_seconds")]
                                                hasError: page.composerState.rangeError !== ""
                                                onEdited: value => composer.editRange("end", value)
                                            }
                                        }
                                    }
                                    RowLayout {
                                        width: parent.width
                                        spacing: 8
                                        UiText {
                                            text: page.composerState.rangeError ? ui.t(page.composerState.rangeError) : ui.t("clip")
                                            color: page.composerState.rangeError ? Theme.error : Theme.muted
                                            font.pixelSize: 12
                                            Layout.fillWidth: true
                                            maximumLineCount: 2
                                            elide: Text.ElideRight
                                        }
                                        UiButton {
                                            objectName: "resetRange"
                                            text: ui.t("reset")
                                            onClicked: composer.resetRange()
                                        }
                                        UiButton {
                                            objectName: "applyRange"
                                            text: ui.t("apply")
                                            onClicked: composer.applyRange()
                                        }
                                        UiButton {
                                            width: 28
                                            ghost: true
                                            compact: true
                                            iconName: "close"
                                            tip: ui.t("close")
                                            onClicked: composer.closeRange()
                                        }
                                    }
                                }
                            }
                            Row {
                                id: extras
                                visible: !page.composerState.isPlaylist
                                width: parent.width
                                height: 40
                                spacing: 8
                                leftPadding: (width - crop.width - (more.visible ? more.width + spacing : 0)) / 2
                                UiButton {
                                    id: crop
                                    objectName: "cropButton"
                                    height: 36
                                    iconName: "trim"
                                    iconSize: 16
                                    horizontalPadding: 10
                                    text: page.composerState.hasRange ? page.composerState.rangeLabel : ui.t("crop")
                                    enabled: !page.composerState.isPlaylist
                                    onClicked: composer.toggleRange()
                                }
                                Item {
                                    id: more
                                    width: tracksButton.implicitWidth
                                    height: 36
                                    UiButton {
                                        id: tracksButton
                                        objectName: "tracksButton"
                                        anchors.fill: parent
                                        enabled: page.composerState.hasExtra
                                        iconName: "captions"
                                        iconSize: 16
                                        text: ui.t("tracks_short")
                                        tip: enabled ? ui.t("more_tracks") : ""
                                        compact: true
                                        Accessible.name: ui.t("more_tracks")
                                        Accessible.description: enabled ? "" : ui.t("tracks_unavailable")
                                        onClicked: tracks.open()
                                    }
                                    // The enabled wrapper receives hover while the
                                    // actual button remains disabled for all input.
                                    HoverHandler {
                                        id: unavailableHover
                                        enabled: !tracksButton.enabled
                                    }
                                    ToolTip {
                                        objectName: "tracksUnavailableTip"
                                        visible: unavailableHover.hovered && !tracksButton.enabled
                                        text: ui.t("tracks_unavailable")
                                        delay: 500
                                        padding: 8
                                        font.family: Theme.fontFamily
                                        font.pixelSize: 12
                                        background: Rectangle {
                                            color: Theme.surface3
                                            border.color: Theme.field
                                            radius: 6
                                        }
                                    }
                                }
                            }
                            Item {
                                height: 12
                                width: 1
                            }
                            UiButton {
                                objectName: "downloadButton"
                                width: parent.width
                                height: 48
                                primary: true
                                iconName: "download"
                                text: ui.t(page.composerState.isPlaylist ? "select_items" : "download_now")
                                enabled: page.composerState.canDownload && !ui.services.closing
                                onClicked: composer.download()
                            }
                            Item {
                                width: 1
                                height: 8
                            }
                            RowLayout {
                                width: parent.width
                                height: 32
                                spacing: 8
                                UiText {
                                    objectName: "outputSummary"
                                    visible: !page.composerState.isPlaylist
                                    text: [page.composerState.container, page.composerState.estimated ? "≈ " + page.composerState.estimated : ""].filter(s => s.length > 0).join(" · ")
                                    font.pixelSize: 12
                                    color: Theme.muted
                                    wrapMode: Text.NoWrap
                                }
                                UiText {
                                    text: ui.settings.state.ask_destination ? ui.t("ask_destination") : ui.settings.state.folder
                                    Layout.fillWidth: true
                                    elide: Text.ElideMiddle
                                    wrapMode: Text.NoWrap
                                    font.pixelSize: 12
                                    color: Theme.muted
                                }
                                UiButton {
                                    id: folderButton
                                    objectName: "changeFolder"
                                    text: ui.t("change_folder")
                                    ghost: true
                                    compact: true
                                    Layout.preferredHeight: 28
                                    Layout.minimumHeight: 28
                                    Layout.maximumHeight: 28
                                    font.pixelSize: 12
                                    onClicked: ui.services.changeFolder()
                                }
                            }
                            UiText {
                                width: parent.width
                                visible: page.composerState.rangeDirty && !page.composerState.rangeOpen
                                text: ui.t("range_pending")
                                color: Theme.warning
                                font.pixelSize: 12
                            }
                        }
                        Rectangle {
                            id: preview
                            objectName: "mediaPreview"
                            visible: workspace.ready
                            anchors.right: parent.right
                            width: workspace.imageWidth
                            height: width * 9 / 16
                            radius: 6
                            color: Theme.surface
                            clip: true
                            Image {
                                id: poster
                                objectName: "previewImage"
                                anchors.fill: parent
                                source: ui.media.source
                                fillMode: Image.PreserveAspectFit
                                smooth: true
                                cache: false
                            }
                            UiText {
                                visible: !ui.media.source
                                anchors.centerIn: parent
                                text: page.composerState.isPlaylist ? page.composerState.duration : ui.t("no_preview")
                                color: Theme.muted
                                font.pixelSize: page.composerState.isPlaylist ? 24 : 12
                            }
                        }
                    }
                }
                Item {
                    visible: ui.queue.count > 0
                    width: 1
                    height: ui.height <= 760 ? 16 : 24
                }
                RowLayout {
                    objectName: "queueHeading"
                    visible: ui.queue.count > 0
                    width: parent.width
                    height: 36
                    UiText {
                        text: ui.t("jobs_files")
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                        Layout.fillWidth: true
                    }
                    UiButton {
                        objectName: "cancelAll"
                        visible: ui.queue.activeCount > 0
                        text: ui.t("cancel_all")
                        ghost: true
                        compact: true
                        font.pixelSize: 12
                        height: 32
                        onClicked: ui.services.cancelAll()
                    }
                    UiButton {
                        objectName: "clearCompleted"
                        visible: ui.queue.clearableCount > 0
                        text: ui.t("clear_list")
                        ghost: true
                        compact: true
                        font.pixelSize: 12
                        height: 32
                        onClicked: ui.services.clearCompleted()
                    }
                }
            }
        }
        delegate: JobRow {
            width: jobs.width
            contentInset: page.ui.contentInset
            ui: page.ui
        }
    }
    TapHandler {
        enabled: page.composerState.rangeOpen
        onTapped: eventPoint => {
            const p = eventPoint.position;
            const editor = jobs.headerItem.rangeItem;
            const trigger = jobs.headerItem.cropItem;
            const r = editor.mapFromItem(page, p.x, p.y);
            const c = trigger.mapFromItem(page, p.x, p.y);
            if (!(r.x >= 0 && r.y >= 0 && r.x <= editor.width && r.y <= editor.height) && !(c.x >= 0 && c.y >= 0 && c.x <= trigger.width && c.y <= trigger.height))
                composer.closeRange();
        }
    }
    Dialog {
        id: tracks
        objectName: "tracksDialog"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: 480
        modal: true
        padding: 24
        background: Rectangle {
            color: Theme.surface
            radius: 6
            border.color: Theme.field
        }
        contentItem: ColumnLayout {
            spacing: 12
            UiText {
                text: ui.t("more_tracks")
                font.pixelSize: 20
                font.weight: Font.DemiBold
            }
            UiText {
                text: ui.t("audio_track")
                color: Theme.muted
                font.pixelSize: 12
            }
            UiCombo {
                objectName: "audioTrackPicker"
                Layout.fillWidth: true
                model: page.composerState.tracks
                value: page.composerState.track
                Accessible.name: ui.t("audio_track")
                onChosen: value => composer.setExtra("track", value)
            }
            UiText {
                visible: page.composerState.mode === "video"
                text: ui.t("subtitles")
                color: Theme.muted
                font.pixelSize: 12
            }
            UiCombo {
                objectName: "subtitlePicker"
                Layout.fillWidth: true
                visible: page.composerState.mode === "video"
                model: page.composerState.subtitles
                value: page.composerState.subtitle
                Accessible.name: ui.t("subtitles")
                onChosen: value => composer.setExtra("subtitle", value)
            }
            UiText {
                objectName: "subtitleStorageHint"
                Layout.fillWidth: true
                visible: page.composerState.mode === "video" && page.composerState.subtitle !== ""
                text: ui.t("subtitles_embedded_hint")
                color: Theme.quiet
                font.pixelSize: 12
            }
            UiButton {
                text: ui.t("close")
                Layout.alignment: Qt.AlignRight
                onClicked: tracks.close()
            }
        }
        Overlay.modal: Rectangle {
            color: "#aa000000"
        }
    }
}
