import QtQuick
import QtQuick.Layouts
import ".."

ColumnLayout {
    id: group
    property alias title: heading.text
    property string headingName: ""
    property bool stretchPanel: false
    default property alias rows: body.data
    spacing: 12
    UiText {
        id: heading
        objectName: group.headingName
        Layout.fillWidth: true
        font.pixelSize: 16
        font.weight: Font.DemiBold
    }
    Rectangle {
        objectName: group.objectName + "Panel"
        Layout.fillWidth: true
        Layout.fillHeight: group.stretchPanel
        implicitHeight: body.implicitHeight + Theme.spaceMedium
        radius: 8
        color: Theme.surface
        border.color: Theme.border
        ColumnLayout {
            id: body
            x: Theme.spaceMedium
            y: Theme.spaceSmall
            width: parent.width - Theme.spaceMedium * 2
            spacing: 0
        }
    }
}
