import QtQuick
import QtQuick.Layouts
import ".."

Item {
    id: feature
    required property var ui
    property string title: ""
    property string description: ""
    property string illustration: ""
    property bool rightColumn: false
    implicitHeight: Math.max(100, copy.implicitHeight + 28)
    Rectangle { anchors.fill: parent; color: Theme.bg }
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: feature.rightColumn ? 24 : 0
        anchors.rightMargin: feature.rightColumn ? 0 : 24
        anchors.topMargin: 14
        anchors.bottomMargin: 14
        spacing: 24
        ColumnLayout {
            id: copy
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: 0
            UiText {
                objectName: feature.objectName + "Title"
                text: feature.title
                Layout.fillWidth: true
                font.weight: Font.DemiBold
                lineHeight: 24
            }
            UiText {
                objectName: feature.objectName + "Description"
                text: feature.description
                Layout.fillWidth: true
                font.pixelSize: 13
                lineHeight: 24
                color: Theme.muted
            }
        }
        FeatureIllustration {
            objectName: feature.objectName + "Illustration"
            ui: feature.ui
            kind: feature.illustration
            Layout.preferredWidth: 144
            Layout.minimumWidth: 144
            Layout.maximumWidth: 144
            Layout.preferredHeight: 64
        }
    }
}
