import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "../components"

Item {
    id: page
    required property var ui
    objectName: "aboutPage"
    Flickable {
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
            width: Math.min(1000, parent.width - 10)
            spacing: 0
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 8
                Layout.bottomMargin: 32
                spacing: 24
                Image { source: ui.services.logo; Layout.preferredWidth: 72; Layout.preferredHeight: 72; sourceSize: Qt.size(144,144); Layout.alignment: Qt.AlignTop }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    UiText { text: "AL Media — AnyLoad Media"; font.pixelSize: 24; font.weight: Font.DemiBold; Layout.fillWidth: true }
                    UiText { text: ui.t("product_description"); color: Theme.muted; Layout.fillWidth: true }
                    UiText { text: ui.t("version") + " " + ui.services.version; font.pixelSize: 12; color: Theme.muted }
                }
            }
            UiText { text: ui.t("supported_sources"); font.pixelSize: 16; font.weight: Font.DemiBold; Layout.bottomMargin: 16 }
            GridLayout {
                Layout.preferredWidth: Math.min(780, content.width)
                Layout.maximumWidth: 780
                columns: 3
                columnSpacing: 32
                rowSpacing: 4
                Repeater {
                    model: [{name:"YouTube",icon:"youtube"},{name:"Facebook",icon:"facebook"},{name:"Instagram",icon:"instagram"},{name:"TikTok",icon:"tiktok"},{name:"SoundCloud",icon:"soundcloud"},{name:"X (Twitter)",icon:"x-twitter"}]
                    Item {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredHeight: 40
                        Row { anchors.verticalCenter: parent.verticalCenter; spacing: 12; UiIcon { name: modelData.icon; tint: Theme.fg; width: 24; height: 24; anchors.verticalCenter: parent.verticalCenter } UiText { text: modelData.name; anchors.verticalCenter: parent.verticalCenter } }
                    }
                }
            }
            UiButton { text: ui.t("all_sites"); iconName: "external"; iconAfter: true; iconSize: 16; horizontalPadding: 0; ghost: true; compact: true; Layout.topMargin: 20; onClicked: ui.services.openSupportedSites() }
            UiText { text: ui.t("availability"); color: Theme.quiet; font.pixelSize: 12; Layout.fillWidth: true; Layout.topMargin: 6 }
            UiRule { Layout.fillWidth: true; Layout.topMargin: 24; Layout.bottomMargin: 24 }
            UiText { text: ui.t("developer"); color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true }
            UiText { text: "Vladislav Galkin (anxthercode)"; Layout.topMargin: 4; Layout.fillWidth: true }
            RowLayout {
                Layout.topMargin: 16
                spacing: 24
                UiText { text: "© 2026 anxthercode"; color: Theme.quiet; font.pixelSize: 12 }
                UiButton { objectName: "licensesButton"; text: ui.t("licenses"); onClicked: ui.showLicenses() }
            }
        }
    }
}
