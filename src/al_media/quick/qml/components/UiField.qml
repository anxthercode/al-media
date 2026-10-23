import QtQuick
import QtQuick.Controls.Basic
import ".."

TextField {
    id: control
    property bool hasError: false
    implicitHeight: 48
    leftPadding: 14
    rightPadding: 14
    topPadding: 0
    bottomPadding: 0
    color: Theme.fg
    placeholderTextColor: Theme.quiet
    selectionColor: Theme.accent
    selectedTextColor: "white"
    font.family: Theme.fontFamily
    font.pixelSize: 14
    renderType: TextInput.NativeRendering
    verticalAlignment: TextInput.AlignVCenter
    selectByMouse: true
    hoverEnabled: true
    onActiveFocusChanged: { if (!activeFocus) deselect(); }
    background: Rectangle {
        radius: 6
        color: Theme.surface
        border.color: control.hasError ? Theme.error : control.activeFocus ? Theme.accent : control.hovered ? Theme.quiet : Theme.field
        Behavior on border.color { ColorAnimation { duration: Theme.motion } }
        Rectangle { anchors.fill: parent; anchors.margins: -4; color: "transparent"; radius: 8; border.color: Theme.accent; border.width: 2; visible: control.activeFocus && control.focusReason === Qt.TabFocusReason }
    }
}
