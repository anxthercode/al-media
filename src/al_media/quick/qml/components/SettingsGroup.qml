import QtQuick
import QtQuick.Layouts
import ".."

ColumnLayout {
    id: group
    property alias title: heading.text
    property string headingName: ""
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
        Layout.fillWidth: true
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
