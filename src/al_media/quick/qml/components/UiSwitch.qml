import QtQuick
import QtQuick.Controls.Basic
import ".."

Switch {
    id: control
    implicitWidth: 40
    implicitHeight: 28
    padding: 0
    hoverEnabled: true
    indicator: Rectangle {
        x: 0
        y: (control.height - height) / 2
        width: 40
        height: 22
        radius: 11
        color: control.checked ? Theme.accent : Theme.surface3
        border.color: control.hovered ? Theme.quiet : control.checked ? Theme.accent : Theme.field
        Rectangle {
            x: control.checked ? 21 : 3
            y: 3
            width: 16
            height: 16
            radius: 8
            color: control.checked ? "white" : Theme.quiet
            Behavior on x { NumberAnimation { duration: Theme.motion } }
        }
        Rectangle { anchors.fill: parent; anchors.margins: -4; color: "transparent"; radius: 14; border.width: 2; border.color: Theme.accent; visible: control.visualFocus }
    }
    contentItem: Item { }
}
