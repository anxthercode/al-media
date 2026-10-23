import QtQuick
import QtQuick.Layouts
import ".."

ColumnLayout {
    property alias text: label.text
    spacing: 20
    UiRule { Layout.fillWidth: true }
    UiText { id: label; font.pixelSize: 16; font.weight: Font.DemiBold; Layout.fillWidth: true }
}
