import QtQuick
import QtQuick.Controls.Basic
import ".."

Column {
    id: section
    property string heading: ""
    property string body: ""
    property string bodyName: ""
    property bool expanded: false
    property bool markdown: false
    signal linkActivated(string url)
    spacing: 0
    Button {
        id: toggle
        objectName: section.bodyName ? section.bodyName + "Toggle" : "licenseToggle"
        width: parent.width
        height: 44
        hoverEnabled: true
        Accessible.name: section.heading
        onClicked: section.expanded = !section.expanded
        background: Rectangle { radius: 4; color: toggle.hovered ? Theme.surface3 : "transparent"; border.color: toggle.visualFocus ? Theme.accent : "transparent" }
        contentItem: Row {
            spacing: 8
            UiIcon {
                name: "chevron"; width: 16; height: 16
                rotation: section.expanded ? 0 : -90
                anchors.verticalCenter: parent.verticalCenter
                Behavior on rotation { NumberAnimation { duration: Theme.reducedMotion ? 0 : 180; easing.type: Easing.OutCubic } }
            }
            UiText { text: section.heading; font.weight: Font.DemiBold; anchors.verticalCenter: parent.verticalCenter }
        }
    }
    Item {
        id: reveal
        width: parent.width
        height: section.expanded && bodyLoader.item ? bodyLoader.item.implicitHeight + 8 : 0
        clip: true
        visible: height > 0
        Behavior on height { NumberAnimation { duration: Theme.reducedMotion ? 0 : 180; easing.type: Easing.OutCubic } }
        Loader {
            id: bodyLoader
            active: section.expanded || reveal.height > 0
            width: parent.width
            y: 8
            sourceComponent: TextArea {
                objectName: section.bodyName
                text: section.body
                textFormat: section.markdown ? TextEdit.MarkdownText : TextEdit.PlainText
                width: section.width
                implicitHeight: contentHeight + 16
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.Wrap
                font.family: Theme.fontFamily
                font.pixelSize: 14
                color: Theme.fg
                leftPadding: 0
                rightPadding: 0
                topPadding: 0
                bottomPadding: 16
                background: null
                onLinkActivated: url => section.linkActivated(url)
            }
        }
    }
    UiRule { width: parent.width }
}
