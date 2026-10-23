import QtQuick
import QtQuick.Controls.Basic
import ".."

ScrollBar {
    id: control
    implicitWidth: 8
    padding: 1
    minimumSize: 0.08
    policy: ScrollBar.AsNeeded
    contentItem: Rectangle {
        implicitWidth: 6
        implicitHeight: 6
        radius: 3
        color: control.pressed || control.hovered ? Theme.quiet : Theme.field
        opacity: control.size < 1 ? 1 : 0
        Behavior on color { ColorAnimation { duration: Theme.motion } }
    }
    background: Item { }
}
