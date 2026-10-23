import QtQuick
import ".."

Item {
    id: control
    property bool running: false
    readonly property bool spinning: spin.running
    implicitWidth: 64
    implicitHeight: 64
    width: implicitWidth
    height: implicitHeight
    visible: running
    Accessible.role: Accessible.ProgressBar
    UiIcon {
        id: ring
        objectName: "spinnerRing"
        anchors.fill: parent
        name: "spinner"
        tint: Theme.accent
        // This motion communicates ongoing work, independently of decorative
        // transition preferences and platform BusyIndicator implementations.
        RotationAnimation on rotation {
            id: spin
            from: 0
            to: 360
            duration: 1100
            loops: Animation.Infinite
            running: control.running && control.visible
        }
    }
}
