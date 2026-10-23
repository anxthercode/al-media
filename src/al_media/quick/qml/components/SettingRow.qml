import QtQuick
import QtQuick.Layouts
import ".."

Item {
    id: row
    property string label: ""
    property bool switchRow: false
    default property alias controls: holder.data
    property real controlWidth: Math.min(440, width * 0.48)
    property real gap: width < 950 ? 24 : 32
    implicitHeight: Math.max(64, labelText.implicitHeight + 16)
    UiText { id: labelText; text: row.label; width: row.width - row.controlWidth - row.gap; anchors.verticalCenter: parent.verticalCenter }
    RowLayout {
        id: holder
        x: row.width - width
        width: row.controlWidth
        height: 48
        anchors.verticalCenter: parent.verticalCenter
        spacing: 10
        layoutDirection: row.switchRow ? Qt.RightToLeft : Qt.LeftToRight
    }
}
