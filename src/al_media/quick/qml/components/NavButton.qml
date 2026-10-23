import QtQuick
import QtQuick.Controls.Basic
import ".."

Button {
    id: control
    property string iconName: "download"
    property bool compact: false
    property bool selected: false
    height: 48
    implicitHeight: 48
    padding: 0
    hoverEnabled: true
    Accessible.name: text
    ToolTip.visible: hovered && compact
    ToolTip.text: text
    ToolTip.delay: 400
    background: Rectangle {
        color: control.selected ? Theme.tint : control.hovered ? Theme.surface3 : "transparent"
        border.width: control.selected ? 1 : 0
        border.color: Theme.navBorder
        radius: 6
        Behavior on color { ColorAnimation { duration: Theme.motion } }
        Rectangle { anchors.fill: parent; anchors.margins: -3; color: "transparent"; radius: 8; border.width: 2; border.color: Theme.accent; visible: control.visualFocus }
    }
    contentItem: Row {
        leftPadding: control.compact ? (control.width - 20) / 2 : 10
        spacing: 12
        UiIcon { anchors.verticalCenter: parent.verticalCenter; name: control.iconName; tint: control.selected ? Theme.accent : Theme.muted }
        UiText { anchors.verticalCenter: parent.verticalCenter; text: control.text; color: control.selected ? Theme.accent : Theme.muted; visible: !control.compact; wrapMode: Text.NoWrap }
    }
}
