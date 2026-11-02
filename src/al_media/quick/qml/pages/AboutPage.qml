import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "../components"

Item {
    id: page
    required property var ui
    readonly property var sourceItems: [
        { name: "YouTube", icon: "youtube" },
        { name: "Facebook", icon: "facebook" },
        { name: "Instagram", icon: "instagram" },
        { name: "Twitch", icon: "twitch" },
        { name: "Pinterest", icon: "pinterest" },
        { name: "TikTok", icon: "tiktok" },
        { name: "SoundCloud", icon: "soundcloud" },
        { name: "X (Twitter)", icon: "x-twitter" },
        { name: "Reddit", icon: "reddit" },
        { name: "Bandcamp", icon: "bandcamp" }
    ]
    objectName: "aboutPage"
    Flickable {
        id: aboutScroll
        objectName: "aboutScroll"
        acceptedButtons: Qt.NoButton
        anchors.fill: parent
        clip: true
        contentWidth: width
        contentHeight: content.y + content.implicitHeight + Theme.spaceLarge
        boundsBehavior: Flickable.StopAtBounds
        UiWheelHandler { scrollBar: aboutBar }
        ScrollBar.vertical: UiScrollBar {
            id: aboutBar
            objectName: "aboutScrollBar"
            parent: page
            edge: true
            scrollTarget: aboutScroll
            upText: ui.t("scroll_up")
            downText: ui.t("scroll_down")
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.right: parent.right
            z: 10
        }
        ColumnLayout {
            id: content
            objectName: "aboutContent"
            x: ui.contentInset
            y: Theme.spaceLarge
            width: aboutScroll.width - ui.contentInset * 2
            spacing: 20
            RowLayout {
                objectName: "aboutProduct"
                Layout.fillWidth: true
                spacing: Theme.spaceLarge
                Image {
                    source: ui.services.logo
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 64
                    sourceSize: Qt.size(128, 128)
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spaceSmall
                    UiText {
                        text: "AL Media — AnyLoad Media"
                        font.pixelSize: 24
                        font.weight: Font.DemiBold
                        lineHeight: 32
                        Layout.fillWidth: true
                    }
                    UiText {
                        text: ui.t("product_description")
                        color: Theme.muted
                        lineHeight: 24
                        Layout.fillWidth: true
                    }
                    RowLayout {
                        objectName: "aboutMetadata"
                        spacing: Theme.spaceMedium
                        UiText {
                            objectName: "aboutVersion"
                            text: ui.t("version") + " " + ui.services.version
                            font.pixelSize: 12
                            color: Theme.muted
                            Layout.alignment: Qt.AlignVCenter
                        }
                        UiLinkButton {
                            objectName: "licensesButton"
                            text: ui.t("licenses")
                            font.pixelSize: 12
                            Layout.preferredHeight: 20
                            onClicked: ui.showLicenses()
                        }
                    }
                }
            }
            ColumnLayout {
                objectName: "aboutOverview"
                Layout.fillWidth: true
                spacing: 20
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 12
                    UiText {
                        text: ui.t("about_features")
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                        lineHeight: 24
                        Layout.fillWidth: true
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: features.implicitHeight + 2
                        color: Theme.border
                        GridLayout {
                            id: features
                            objectName: "aboutFeatures"
                            x: 0
                            y: 1
                            width: parent.width
                            columns: 2
                            uniformCellWidths: true
                            uniformCellHeights: true
                            columnSpacing: 1
                            rowSpacing: 1
                            Repeater {
                                model: ["media", "fragments", "queue", "files"]
                                FeatureItem {
                                    required property string modelData
                                    required property int index
                                    objectName: "aboutFeature-" + modelData
                                    ui: page.ui
                                    Layout.fillWidth: true
                                    Layout.preferredWidth: 1
                                    Layout.minimumWidth: 0
                                    Layout.fillHeight: true
                                    rightColumn: index % 2 === 1
                                    title: ui.t("about_" + modelData + "_title")
                                    description: ui.t("about_" + modelData + "_body")
                                    illustration: modelData
                                }
                            }
                        }
                    }
                }
                ColumnLayout {
                    objectName: "aboutSources"
                    Layout.fillWidth: true
                    spacing: 12
                    UiText {
                        text: ui.t("supported_sources")
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                        lineHeight: 24
                        Layout.fillWidth: true
                    }
                    Item {
                        id: sources
                        objectName: "sourcesGrid"
                        Layout.fillWidth: true
                        implicitHeight: Math.ceil(page.sourceItems.length / columns) * 48 - 12
                        readonly property int columns: 5
                        readonly property real cellWidth: 44 + Math.ceil(page.sourceItems.reduce((longest, source) => Math.max(longest, sourceMetrics.advanceWidth(source.name)), 0))
                        readonly property real columnSpacing: Math.max(16, (width - cellWidth * columns) / (columns - 1))
                        FontMetrics { id: sourceMetrics; font.family: Theme.fontFamily; font.pixelSize: 14 }
                        Repeater {
                            model: page.sourceItems
                            RowLayout {
                                required property var modelData
                                required property int index
                                objectName: "source-" + modelData.icon
                                x: index % sources.columns * (sources.cellWidth + sources.columnSpacing)
                                y: Math.floor(index / sources.columns) * 48
                                width: sources.cellWidth
                                height: 36
                                spacing: Theme.spaceSmall
                                Item {
                                    Layout.preferredWidth: 32
                                    Layout.minimumWidth: 32
                                    Layout.maximumWidth: 32
                                    Layout.preferredHeight: 32
                                    UiIcon {
                                        anchors.centerIn: parent
                                        name: modelData.icon
                                        tint: Theme.fg
                                        width: 24
                                        height: 24
                                    }
                                }
                                UiText {
                                    text: modelData.name
                                    Layout.fillWidth: true
                                    wrapMode: Text.NoWrap
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }
                    UiLinkButton {
                        objectName: "allSourcesButton"
                        text: ui.t("all_sites")
                        iconName: "external"
                        Layout.preferredHeight: 24
                        onClicked: ui.services.openSupportedSites()
                    }
                }
            }
            ColumnLayout {
                objectName: "aboutDeveloper"
                Layout.fillWidth: true
                Layout.topMargin: Theme.spaceSmall
                spacing: 20
                UiRule { objectName: "aboutDivider"; Layout.fillWidth: true }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spaceLarge
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        UiText {
                            text: ui.t("developer")
                            color: Theme.quiet
                            font.pixelSize: 12
                            lineHeight: 20
                            Layout.fillWidth: true
                        }
                        UiText {
                            text: "Vladislav Galkin (anxthercode)"
                            color: Theme.muted
                            lineHeight: 24
                            Layout.fillWidth: true
                        }
                    }
                    UiText {
                        text: "© 2026 anxthercode"
                        color: Theme.quiet
                        font.pixelSize: 12
                        lineHeight: 20
                        Layout.alignment: Qt.AlignBottom
                    }
                }
            }
        }
    }
}
