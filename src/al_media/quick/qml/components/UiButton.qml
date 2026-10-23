import QtQuick
import QtQuick.Controls.Basic
import ".."

Button {
    id: control
    property bool primary: false
    property bool ghost: false
    property bool selected: false
    property bool compact: false
    property string iconName: ""
    property string tip: ""
    property bool iconAfter: false
    property int iconSize: 20
    property real iconRotation: 0
    horizontalPadding: compact ? 8 : 14
    implicitWidth: contentRow.implicitWidth + horizontalPadding * 2
    implicitHeight: primary ? 48 : 36
    padding: 0
    hoverEnabled: true
    opacity: enabled ? 1 : 0.42
    font.family: Theme.fontFamily
    font.pixelSize: 14
    Accessible.name: text || tip
    ToolTip.visible: hovered && tip.length > 0
    ToolTip.text: tip
    ToolTip.delay: 500
    background: Rectangle {
        radius: 6
        color: control.primary ? (control.hovered ? Theme.primaryHover : Theme.primary) : control.selected ? Theme.tint : control.hovered ? Theme.surface3 : control.ghost ? "transparent" : Theme.surface2
        border.width: control.primary || control.ghost && !control.selected ? 0 : 1
        border.color: control.selected ? Theme.navBorder : control.hovered ? Theme.quiet : Theme.field
        Behavior on color { ColorAnimation { duration: Theme.motion } }
        Rectangle { anchors.fill: parent; anchors.margins: -4; radius: 8; color: "transparent"; border.width: 2; border.color: Theme.accent; visible: control.visualFocus }
    }
    contentItem: Item {
        Row {
            id: contentRow
            anchors.centerIn: parent
            spacing: 8
            layoutDirection: control.iconAfter ? Qt.RightToLeft : Qt.LeftToRight
            UiIcon {
                visible: control.iconName.length > 0; name: control.iconName
                width: control.iconSize; height: control.iconSize
                tint: control.primary ? "white" : control.selected ? Theme.accent : control.hovered ? Theme.fg : Theme.muted
                anchors.verticalCenter: parent.verticalCenter
                rotation: control.iconRotation
                Behavior on rotation { NumberAnimation { duration: Theme.reducedMotion ? 0 : 180; easing.type: Easing.OutCubic } }
            }
            UiText { visible: text.length > 0; text: control.text; color: control.primary ? "white" : control.selected ? Theme.accent : Theme.fg; font.pixelSize: control.font.pixelSize; font.weight: control.primary ? Font.DemiBold : control.font.weight; wrapMode: Text.NoWrap; anchors.verticalCenter: parent.verticalCenter }
        }
    }
}
