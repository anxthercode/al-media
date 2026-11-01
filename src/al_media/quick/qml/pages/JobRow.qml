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
    property bool pooled: false
    ListView.onPooled: pooled = true
    ListView.onReused: pooled = false
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
            Layout.minimumWidth: 0
            Layout.alignment: Qt.AlignTop
            spacing: 4
            UiText { text: row.title; font.weight: Font.DemiBold; Layout.fillWidth: true; maximumLineCount: 2; elide: Text.ElideRight }
            UiText { text: row.metadata; font.pixelSize: 12; color: Theme.muted; Layout.fillWidth: true; maximumLineCount: 2; elide: Text.ElideRight }
            UiText { text: row.error; visible: text.length > 0; color: Theme.error; font.pixelSize: 12; Layout.fillWidth: true }
        }
        Column {
            objectName: "statusColumn-" + row.taskId
            Layout.alignment: Qt.AlignTop
            Layout.preferredWidth: Math.min(420, row.width * 0.36)
            Layout.minimumWidth: Math.min(420, row.width * 0.36)
            Layout.maximumWidth: Math.min(420, row.width * 0.36)
            spacing: 5
            RowLayout {
                width: parent.width
                UiText { text: row.status; font.pixelSize: 12; color: row.taskState === "failed" ? Theme.error : row.taskState === "postprocessing" || row.taskState === "completed" && !row.canOpen ? Theme.warning : Theme.muted; Layout.fillWidth: true }
                UiText { text: Math.floor(row.progress) + "%"; visible: row.taskState === "downloading" && !row.indeterminate; font.pixelSize: 12; font.weight: Font.DemiBold }
            }
            UiProgress {
                objectName: "taskProgress-" + row.taskId
                width: parent.width
                height: 4
                visible: row.canCancel
                value: row.progress
                indeterminate: row.indeterminate
                animate: !row.pooled
                tint: row.taskState === "postprocessing" ? Theme.warning : Theme.muted
            }
            UiText { objectName: "taskDetail-" + row.taskId; width: parent.width; height: 18; text: row.detail; color: Theme.quiet; font.pixelSize: 12; maximumLineCount: 1; elide: Text.ElideMiddle }
        }
        Item {
            Layout.preferredWidth: ui.jobActionsWidth
            Layout.minimumWidth: ui.jobActionsWidth
            Layout.maximumWidth: ui.jobActionsWidth
            Layout.preferredHeight: 36
            Row {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6
                UiButton { objectName: "cancelTask-" + row.taskId; text: ui.t("cancel"); ghost: true; compact: true; visible: row.canCancel; onClicked: ui.services.cancelTask(row.taskId) }
                UiButton { objectName: "retryTask-" + row.taskId; text: ui.t("retry"); ghost: true; compact: true; visible: row.canRetry; onClicked: ui.services.retryTask(row.taskId) }
                UiButton { objectName: "openResult-" + row.taskId; iconName: "play"; text: ui.t("open"); visible: row.canOpen; onClicked: ui.services.openResult(row.taskId, false) }
                UiButton { objectName: "showFolder-" + row.taskId; width: 36; iconName: "folderOpen"; tip: ui.t("folder"); ghost: true; compact: true; visible: row.canOpen; onClicked: ui.services.openResult(row.taskId, true) }
                UiButton { objectName: "removeTask-" + row.taskId; width: 36; iconName: "close"; tip: ui.t("remove"); ghost: true; compact: true; visible: !row.canCancel; onClicked: ui.services.removeTask(row.taskId) }
            }
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
