import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "../components"

Item {
    id: row
    required property var ui
    required property string taskId
    required property string title
    required property string metadata
    required property string status
    required property string taskState
    required property real progress
    required property bool indeterminate
    required property string detail
    required property string error
    required property bool canCancel
    required property bool canRetry
    required property bool canOpen
    required property string sourceUrl
    required property string destination
    objectName: "downloadRow-" + taskId
    height: Math.max(80, mainRow.implicitHeight + 24)
    RowLayout {
        id: mainRow
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.topMargin: 12
        spacing: ui.compact ? 16 : 24
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4
            UiText { text: row.title; font.weight: Font.DemiBold; Layout.fillWidth: true; maximumLineCount: 2; elide: Text.ElideRight }
            UiText { text: row.metadata; font.pixelSize: 12; color: Theme.muted; Layout.fillWidth: true; maximumLineCount: 2; elide: Text.ElideRight }
            UiText { text: row.error; visible: text.length > 0; color: Theme.error; font.pixelSize: 12; Layout.fillWidth: true }
        }
        Column {
            Layout.preferredWidth: ui.compact ? 210 : 280
            spacing: 5
            RowLayout {
                width: parent.width
                UiText { text: row.status; font.pixelSize: 12; color: row.taskState === "failed" ? Theme.error : row.taskState === "postprocessing" ? Theme.warning : Theme.muted; Layout.fillWidth: true }
                UiText { text: Math.floor(row.progress) + "%"; visible: row.taskState === "downloading" && !row.indeterminate; font.pixelSize: 12; font.weight: Font.DemiBold }
            }
            ProgressBar {
                width: parent.width
                height: 3
                visible: !row.canOpen && row.taskState !== "failed" && row.taskState !== "cancelled" && row.taskState !== "interrupted"
                from: 0; to: 100; value: row.progress
                indeterminate: row.indeterminate
                background: Rectangle { color: Theme.surface3; radius: 2 }
                contentItem: Item {
                    clip: true
                    Rectangle {
                        width: parent.width * (row.indeterminate ? 0.3 : row.progress / 100)
                        height: parent.height
                        color: row.taskState === "postprocessing" ? Theme.warning : Theme.muted
                        x: 0
                        SequentialAnimation on x { running: row.indeterminate && row.visible && !Theme.reducedMotion; loops: Animation.Infinite; NumberAnimation { from: -84; to: 280; duration: 1400 } }
                    }
                }
            }
            UiText { width: parent.width; text: row.detail; color: Theme.quiet; font.pixelSize: 12; maximumLineCount: 1; elide: Text.ElideMiddle }
        }
        Row {
            spacing: 6
            UiButton { objectName: "cancelTask-" + row.taskId; text: ui.t("cancel"); ghost: true; compact: true; visible: row.canCancel; onClicked: ui.services.cancelTask(row.taskId) }
            UiButton { objectName: "retryTask-" + row.taskId; text: ui.t("retry"); ghost: true; compact: true; visible: row.canRetry; onClicked: ui.services.retryTask(row.taskId) }
            UiButton { objectName: "openResult-" + row.taskId; iconName: "play"; text: ui.t("open"); visible: row.canOpen; onClicked: ui.services.openResult(row.taskId, false) }
            UiButton { objectName: "showFolder-" + row.taskId; width: 36; iconName: "folder"; tip: ui.t("folder"); ghost: true; compact: true; visible: row.canOpen; onClicked: ui.services.openResult(row.taskId, true) }
            UiButton { objectName: "removeTask-" + row.taskId; width: 36; iconName: "close"; tip: ui.t("remove"); ghost: true; compact: true; visible: !row.canCancel; onClicked: ui.services.removeTask(row.taskId) }
        }
    }
    UiRule { width: parent.width; anchors.bottom: parent.bottom }
    TapHandler { acceptedButtons: Qt.RightButton; onTapped: actionsMenu.popup() }
    Menu {
        id: actionsMenu
        MenuItem { text: ui.t("open"); visible: row.canOpen; onTriggered: ui.services.openResult(row.taskId, false) }
        MenuItem { text: ui.t("folder"); visible: row.canOpen; onTriggered: ui.services.openResult(row.taskId, true) }
        MenuItem { text: ui.t("remove"); enabled: !row.canCancel; onTriggered: ui.services.removeTask(row.taskId) }
    }
}
