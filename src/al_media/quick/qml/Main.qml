import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Window
import "."
import "components"
import "pages"

ApplicationWindow {
    id: root
    required property QtObject services
    readonly property var composer: services.composer
    readonly property var settings: services.settings
    readonly property var queue: services.downloads
    readonly property var media: services.media
    readonly property string globalError: services.feedback || (settings.state.error !== "concurrency_invalid" ? settings.state.error : "")
    readonly property bool compact: width <= 1100
    readonly property int pagePadding: compact ? 20 : 28
    readonly property int headerHeight: height <= 760 ? 60 : 64
    property bool systemLight: Application.styleHints.colorScheme === Qt.Light
    property bool reducedMotion: false
    property string uiFontFamily: "Segoe UI"
    width: 1280
    height: 800
    minimumWidth: 1024
    minimumHeight: 640
    title: "AL Media"
    color: Theme.bg
    font.family: Theme.fontFamily
    font.pixelSize: 14
    palette.window: Theme.surface
    palette.windowText: Theme.fg
    palette.base: Theme.surface
    palette.text: Theme.fg
    palette.button: Theme.surface2
    palette.buttonText: Theme.fg
    palette.highlight: Theme.accent
    palette.highlightedText: "white"
    palette.toolTipBase: Theme.surface3
    palette.toolTipText: Theme.fg
    objectName: "quickWindow"
    function t(key) { const language = settings.state.language; return services.localization.text(key); }
    function showLicenses() { licenses.open(); }
    Binding { target: Theme; property: "light"; value: root.settings.state.theme === "light" || root.settings.state.theme === "system" && root.systemLight }
    Binding { target: Theme; property: "reducedMotion"; value: root.reducedMotion }
    Binding { target: Theme; property: "fontFamily"; value: root.uiFontFamily }
    onClosing: close => { close.accepted = services.requestClose(); }
    onVisibilityChanged: visibility => media.setActive(visible && visibility !== Window.Minimized && services.page === "downloads")
    Shortcut { sequence: "Ctrl+L"; onActivated: { services.navigate("downloads"); downloads.focusUrl(); } }
    Shortcut { sequence: "Escape"; enabled: composer.state.rangeOpen; onActivated: composer.closeRange() }
    RowLayout {
        enabled: !services.closing
        anchors.fill: parent
        spacing: 0
        Rectangle {
            id: sidebar
            Layout.preferredWidth: root.compact ? 72 : root.width >= 1700 ? 208 : 176
            Layout.fillHeight: true
            color: Theme.surface
            Rectangle { anchors.right: parent.right; height: parent.height; width: 1; color: Theme.border }
            ColumnLayout {
                anchors.fill: parent
                spacing: 0
                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: root.headerHeight
                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        x: root.compact ? (parent.width - 26) / 2 : 20
                        spacing: 12
                        Image { source: services.logo; width: 26; height: 26; sourceSize: Qt.size(52, 52); anchors.verticalCenter: parent.verticalCenter; smooth: true }
                        UiText { text: "AL Media"; font.pixelSize: 18; font.weight: Font.DemiBold; visible: !root.compact; anchors.verticalCenter: parent.verticalCenter; wrapMode: Text.NoWrap }
                    }
                    UiRule { anchors.bottom: parent.bottom; width: parent.width }
                }
                Column {
                    Layout.fillWidth: true
                    Layout.margins: 10
                    Layout.topMargin: 20
                    spacing: 8
                    NavButton { objectName: "navDownloads"; width: parent.width; text: root.t("downloads"); iconName: "download"; compact: root.compact; selected: services.page === "downloads"; onClicked: services.navigate("downloads") }
                    NavButton { objectName: "navSettings"; width: parent.width; text: root.t("settings"); iconName: "settings"; compact: root.compact; selected: services.page === "settings"; onClicked: services.navigate("settings") }
                }
                Item { Layout.fillHeight: true }
                NavButton { objectName: "navAbout"; Layout.fillWidth: true; Layout.margins: 10; Layout.bottomMargin: 20; text: root.t("about"); iconName: "info"; compact: root.compact; selected: services.page === "about"; onClicked: services.navigate("about") }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: root.headerHeight
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: root.pagePadding
                    anchors.rightMargin: root.pagePadding
                    UiText { text: root.t(services.page); font.pixelSize: 28; font.weight: Font.DemiBold; font.letterSpacing: -0.5; Layout.fillWidth: true; wrapMode: Text.NoWrap }
                    UiText { text: services.closing ? root.t("postprocessing") + "…" : root.globalError ? root.t(root.globalError) : ""; color: Theme.error; font.pixelSize: 12; Layout.maximumWidth: 420 }
                }
                UiRule { anchors.bottom: parent.bottom; width: parent.width }
            }
            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: services.page === "downloads" ? 0 : services.page === "settings" ? 1 : 2
                DownloadsPage { id: downloads; ui: root }
                SettingsPage { id: settingsPage; ui: root }
                AboutPage { ui: root }
            }
        }
    }
    DropArea {
        anchors.fill: parent
        onDropped: drop => {
            if (drop.hasUrls && drop.urls.length === 1 && String(drop.urls[0]).toLowerCase().endsWith(".txt")) services.importTextFile(String(drop.urls[0]));
            else if (drop.hasText) { services.navigate("downloads"); composer.setUrl(drop.text); composer.pasted(); }
        }
    }
    Connections {
        target: services
        function onFocusFolder() { Qt.callLater(settingsPage.focusFolder); }
        function onReturnToComposer() { downloads.focusReturn(); }
        function onDuplicateRequested() { duplicate.open(); }
        function onPlaylistRequested() {
            playlist.selectedIds = services.playlistEntries.filter(e => e.url.length > 0).map(e => e.index);
            playlist.open();
        }
    }
    Dialog {
        id: duplicate
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(480, root.width - 48)
        modal: true
        title: root.t("duplicate")
        padding: 24
        background: Rectangle { color: Theme.surface; border.color: Theme.field; radius: 6 }
        header: UiText { text: duplicate.title; font.pixelSize: 20; font.weight: Font.DemiBold; padding: 24; bottomPadding: 0 }
        contentItem: ColumnLayout {
            spacing: 24
            UiText { text: root.t("repeat_question"); Layout.fillWidth: true }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                UiButton { text: root.t("cancel"); onClicked: duplicate.reject() }
                UiButton { text: root.t("open"); visible: services.duplicateCanOpen; onClicked: { services.openDuplicate(); duplicate.accept(); } }
                UiButton { text: root.t("download_again"); primary: true; onClicked: { services.confirmDuplicate(true, true); duplicate.accept(); } }
            }
        }
        onRejected: services.confirmDuplicate(false, false)
        Overlay.modal: Rectangle { color: "#aa000000" }
    }
    Dialog {
        id: playlist
        property var selectedIds: []
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(640, root.width - 48)
        height: Math.min(560, root.height - 48)
        modal: true
        padding: 24
        background: Rectangle { color: Theme.surface; border.color: Theme.field; radius: 6 }
        header: UiText { text: root.t("select_items"); font.pixelSize: 20; font.weight: Font.DemiBold; padding: 24; bottomPadding: 0 }
        contentItem: ColumnLayout {
            spacing: 12
            RowLayout {
                UiButton { text: root.t("select_all"); onClicked: playlist.selectedIds = services.playlistEntries.filter(e => e.url.length > 0).map(e => e.index) }
                UiButton { text: root.t("select_none"); onClicked: playlist.selectedIds = [] }
            }
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: services.playlistEntries
                delegate: UiCheck {
                    required property var modelData
                    width: ListView.view.width
                    text: modelData.title
                    enabled: modelData.url.length > 0
                    checked: playlist.selectedIds.indexOf(modelData.index) >= 0
                    onToggled: { let rows = playlist.selectedIds.slice(); if (checked) rows.push(modelData.index); else rows = rows.filter(i => i !== modelData.index); playlist.selectedIds = rows; }
                }
                ScrollBar.vertical: ScrollBar { }
            }
            RowLayout {
                UiText { text: playlist.selectedIds.length + " / " + services.playlistEntries.length; Layout.fillWidth: true; color: Theme.muted }
                UiButton { text: root.t("cancel"); onClicked: playlist.reject() }
                UiButton { text: root.t("download_now"); primary: true; enabled: playlist.selectedIds.length > 0; onClicked: { services.acceptPlaylist(playlist.selectedIds); playlist.accept(); } }
            }
        }
        Overlay.modal: Rectangle { color: "#aa000000" }
    }
    Dialog {
        id: licenses
        objectName: "licensesDialog"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(760, root.width - 48)
        height: Math.min(794, root.height - 64)
        modal: true
        padding: 0
        background: Rectangle { color: Theme.surface; border.color: Theme.field; radius: 6 }
        header: UiText { text: root.t("licenses"); leftPadding: 24; rightPadding: 24; topPadding: 20; bottomPadding: 20; lineHeight: font.pixelSize * 1.3; font.pixelSize: 24; font.weight: Font.DemiBold; UiRule { width: parent.width; anchors.bottom: parent.bottom } }
        contentItem: Flickable {
            id: licenseScroll
            objectName: "licenseScroll"
            clip: true
            contentWidth: width
            contentHeight: licenseContent.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            acceptedButtons: Qt.NoButton
            onContentHeightChanged: { if (contentY > Math.max(0, contentHeight - height)) contentY = Math.max(0, contentHeight - height); }
            ScrollBar.vertical: UiScrollBar { objectName: "licenseScrollBar"; width: 8; anchors.right: parent.right; anchors.rightMargin: 4 }
            Column {
                id: licenseContent
                width: licenseScroll.width
                leftPadding: 24
                rightPadding: 24
                topPadding: 8
                bottomPadding: 24
                spacing: 12
                LicenseSection { objectName: "mainLicenseSection"; width: parent.width - 48; heading: "AL Media — MIT"; body: services.licenseText; bodyName: "licenseBody"; expanded: true }
                Repeater {
                    model: services.licenseSections
                    LicenseSection { required property var modelData; width: parent.width - 48; heading: modelData.title; body: modelData.body; markdown: true; onLinkActivated: url => services.openLicenseLink(url) }
                }
            }
        }
        footer: Item { height: 76; UiRule { width: parent.width } UiButton { objectName: "closeLicenses"; anchors.right: parent.right; anchors.rightMargin: 24; anchors.verticalCenter: parent.verticalCenter; text: root.t("close"); onClicked: licenses.close() } }
        Overlay.modal: Rectangle { color: "#aa000000" }
    }
}
