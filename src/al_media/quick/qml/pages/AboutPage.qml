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
        id: aboutScroll
        objectName: "aboutScroll"
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
        ScrollBar.vertical: UiScrollBar {
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
            width: Math.min(1000, parent.width - 10)
            spacing: 0
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 8
                Layout.bottomMargin: Theme.sectionSpace
                spacing: Theme.spaceLarge
                Image {
                    source: ui.services.logo
                    Layout.preferredWidth: 72
                    Layout.preferredHeight: 72
                    sourceSize: Qt.size(144, 144)
                    Layout.alignment: Qt.AlignTop
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    UiText {
                        text: "AL Media — AnyLoad Media"
                        font.pixelSize: 24
                        font.weight: Font.DemiBold
                        Layout.fillWidth: true
                    }
                    UiText {
                        text: ui.t("product_description")
                        color: Theme.muted
                        Layout.fillWidth: true
                    }
                    RowLayout {
                        objectName: "aboutMetadata"
                        spacing: Theme.spaceMedium
                        UiText {
                            text: ui.t("version") + " " + ui.services.version
                            font.pixelSize: 12
                            color: Theme.muted
                        }
                        UiButton {
                            objectName: "licensesButton"
                            text: ui.t("licenses")
                            ghost: true
                            compact: true
                            onClicked: ui.showLicenses()
                        }
                    }
                }
            }
            GridLayout {
                objectName: "aboutFeatures"
                Layout.fillWidth: true
                Layout.bottomMargin: Theme.sectionSpace
                columns: width >= 640 ? 2 : 1
                columnSpacing: Theme.spaceLarge
                rowSpacing: Theme.spaceMedium
                Repeater {
                    model: ["media", "fragments", "queue", "files"]
                    RowLayout {
                        required property string modelData
                        objectName: "aboutFeature-" + modelData
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        Layout.minimumWidth: 0
                        Layout.alignment: Qt.AlignTop
                        spacing: 10
                        UiIcon {
                            objectName: "aboutFeatureIcon-" + modelData
                            Layout.preferredWidth: 18
                            Layout.preferredHeight: 18
                            Layout.alignment: Qt.AlignTop
                            Layout.topMargin: 2
                            tint: Theme.muted
                            name: ({
                                       media: "video",
                                       fragments: "trim",
                                       queue: "download",
                                       files: "folder"
                                   })[modelData]
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            spacing: 6
                            UiText {
                                text: ui.t("about_" + modelData + "_title")
                                font.weight: Font.DemiBold
                                Layout.fillWidth: true
                            }
                            UiText {
                                text: ui.t("about_" + modelData + "_body")
                                font.pixelSize: 12
                                color: Theme.muted
                                Layout.fillWidth: true
                            }
                        }
                    }
                }
            }
            UiText {
                Layout.fillWidth: true
                Layout.bottomMargin: Theme.spaceMedium
                text: ui.t("supported_sources")
                font.pixelSize: 16
                font.weight: Font.DemiBold
            }
            GridLayout {
                id: sources
                objectName: "sourcesGrid"
                Layout.fillWidth: true
                columns: width >= 640 ? 4 : 2
                columnSpacing: Theme.spaceLarge
                rowSpacing: Theme.spaceSmall
                Repeater {
                    model: [
                        {
                            name: "YouTube",
                            icon: "youtube"
                        },
                        {
                            name: "Facebook",
                            icon: "facebook"
                        },
                        {
                            name: "Instagram",
                            icon: "instagram"
                        },
                        {
                            name: "Twitch",
                            icon: "twitch"
                        },
                        {
                            name: "TikTok",
                            icon: "tiktok"
                        },
                        {
                            name: "SoundCloud",
                            icon: "soundcloud"
                        },
                        {
                            name: "X (Twitter)",
                            icon: "x-twitter"
                        },
                        {
                            name: "Reddit",
                            icon: "reddit"
                        }
                    ]
                    Item {
                        required property var modelData
                        objectName: "source-" + modelData.icon
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        Layout.minimumWidth: 0
                        Layout.preferredHeight: 40
                        RowLayout {
                            anchors.fill: parent
                            spacing: 12
                            UiIcon {
                                name: modelData.icon
                                tint: Theme.fg
                                Layout.preferredWidth: 24
                                Layout.preferredHeight: 24
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
            }
            ColumnLayout {
                objectName: "allSourcesArea"
                Layout.fillWidth: true
                Layout.topMargin: Theme.spaceMedium
                spacing: Theme.spaceSmall
                UiButton {
                    objectName: "allSourcesButton"
                    text: ui.t("all_sites")
                    iconName: "external"
                    iconAfter: true
                    iconSize: 16
                    ghost: true
                    horizontalPadding: 12
                    Layout.preferredHeight: 36
                    onClicked: ui.services.openSupportedSites()
                }
                UiText {
                    objectName: "sourcesAvailability"
                    text: ui.t("availability")
                    color: Theme.quiet
                    font.pixelSize: 12
                    Layout.fillWidth: true
                }
            }
            UiRule {
                objectName: "aboutDivider"
                Layout.fillWidth: true
                Layout.topMargin: Theme.spaceLarge
                Layout.bottomMargin: Theme.spaceLarge
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spaceLarge
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    UiText {
                        text: ui.t("developer")
                        color: Theme.muted
                        font.pixelSize: 12
                        Layout.fillWidth: true
                    }
                    UiText {
                        text: "Vladislav Galkin (anxthercode)"
                        Layout.fillWidth: true
                    }
                    UiText {
                        text: "© 2026 anxthercode"
                        color: Theme.quiet
                        font.pixelSize: 12
                    }
                }
            }
        }
    }
}
