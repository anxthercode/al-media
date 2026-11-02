import QtQuick
import QtQuick.Controls.Basic
import ".."

Button {
    id: control
    property string iconName: ""
    implicitWidth: contents.implicitWidth + rightPadding
    implicitHeight: 36
    leftPadding: 0
    rightPadding: 4
    topPadding: 0
    bottomPadding: 0
    hoverEnabled: true
    font.family: Theme.fontFamily
    font.pixelSize: 14
    Accessible.name: text
    contentItem: Row {
        id: contents
        spacing: 8
        UiText {
            objectName: control.objectName + "Text"
            text: control.text
            font.pixelSize: control.font.pixelSize
            font.underline: control.hovered
            color: Theme.accent
            anchors.verticalCenter: parent.verticalCenter
            wrapMode: Text.NoWrap
        }
        UiIcon {
            visible: control.iconName.length > 0
            name: control.iconName
            width: 16
            height: 16
            tint: Theme.accent
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    background: Rectangle {
        color: "transparent"
        radius: 4
        border.width: control.visualFocus ? 2 : 0
        border.color: Theme.accent
    }
}
