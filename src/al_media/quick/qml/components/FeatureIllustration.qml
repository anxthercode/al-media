import QtQuick
import ".."

Item {
    id: illustration
    required property var ui
    required property string kind
    implicitWidth: 144
    implicitHeight: 64
    Accessible.ignored: true

    component Caption: UiText {
        font.pixelSize: 12
        lineHeight: 20
        color: Theme.muted
        wrapMode: Text.NoWrap
        horizontalAlignment: Text.AlignHCenter
        Accessible.ignored: true
    }

    Item {
        anchors.fill: parent
        visible: illustration.kind === "media"
        UiIcon { anchors.fill: parent; name: "about-media"; tint: Theme.muted }
        Rectangle { x: 64; y: 8; width: 1; height: 48; color: Theme.field }
        Caption { x: 0; y: 40; width: 56; text: ui.t("video_mode") }
        Caption { x: 68; y: 40; width: 76; text: "MP3 · M4A" }
    }
    Item {
        anchors.fill: parent
        visible: illustration.kind === "fragments"
        UiIcon { anchors.fill: parent; name: "about-timeline"; tint: Theme.field }
        Rectangle {
            x: 40; y: 12; width: 64; height: 24; radius: 4
            color: Qt.tint(Theme.surface, Theme.tint)
            border.width: 1.5
            border.color: Theme.accent
        }
        UiIcon { anchors.fill: parent; name: "about-range"; tint: Theme.accent }
        Caption { y: 42; width: parent.width; text: ui.t("audio_mode") + " · " + ui.t("subtitles") }
    }
    Item {
        anchors.fill: parent
        visible: illustration.kind === "queue"
        UiIcon { anchors.fill: parent; name: "about-queue"; tint: Theme.field }
        UiIcon { x: 8; y: 8; width: 12; height: 12; name: "check"; tint: Theme.muted }
        UiIcon { x: 8; y: 44; width: 12; height: 12; name: "check"; tint: Theme.muted }
        Caption {
            x: 80; y: 16; width: 64
            text: ui.t("about_diagram_limit")
            font.pixelSize: 14
            font.weight: Font.DemiBold
            color: Theme.fg
        }
        Caption { x: 80; y: 34; width: 64; text: ui.t("about_diagram_downloads") }
    }
    Item {
        anchors.fill: parent
        visible: illustration.kind === "files"
        UiIcon { x: 4; y: 20; width: 24; height: 24; name: "folder"; tint: Theme.muted }
        Caption { x: 40; y: 12; width: 104; horizontalAlignment: Text.AlignLeft; text: ui.t("about_diagram_name") }
        Caption { x: 40; y: 34; width: 104; horizontalAlignment: Text.AlignLeft; text: ui.t("about_diagram_tags") }
    }
}
