import QtQuick
import QtQuick.Controls.Basic
import ".."

CheckBox {
    id: control
    spacing: 10
    implicitHeight: 36
    hoverEnabled: true
    font.family: Theme.fontFamily
    font.pixelSize: 14
    indicator: Rectangle {
        implicitWidth: 18
        implicitHeight: 18
        x: control.leftPadding
        y: (control.height - height) / 2
        radius: 4
        color: control.checked ? Theme.accent : Theme.surface
        border.color: control.visualFocus || control.hovered ? Theme.accent : Theme.quiet
        UiIcon { name: "check"; width: 16; height: 16; anchors.centerIn: parent; tint: "white"; visible: control.checked }
    }
    contentItem: UiText { text: control.text; leftPadding: control.indicator.width + control.spacing; verticalAlignment: Text.AlignVCenter }
}
