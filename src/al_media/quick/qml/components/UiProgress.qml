import QtQuick
import ".."

Item {
    id: control
    property real value: 0
    property bool indeterminate: false
    property bool animate: true
    property color tint: Theme.muted
    property real phase: 0
    readonly property real fraction: Math.max(0, Math.min(1, value / 100))
    readonly property bool spinning: pulseAnimation.running
    implicitHeight: 4
    clip: true
    Accessible.role: Accessible.ProgressBar
    Rectangle { anchors.fill: parent; radius: height / 2; color: Theme.surface3 }
    // Separate items ensure a stopped waiting animation can never displace
    // the known percentage, including when ListView reuses a delegate.
    Rectangle {
        objectName: "determinateFill"
        visible: !control.indeterminate
        x: 0
        width: control.width * control.fraction
        height: parent.height
        radius: height / 2
        color: control.tint
    }
    Rectangle {
        id: pulse
        visible: control.indeterminate
        width: control.width * 0.28
        height: parent.height
        radius: height / 2
        color: control.tint
        x: Theme.reducedMotion ? (control.width - width) / 2 : control.phase * (control.width + width) - width
    }
    NumberAnimation on phase {
        id: pulseAnimation
        from: 0
        to: 1
        duration: 1400
        loops: Animation.Infinite
        running: control.indeterminate && control.animate && control.visible && !Theme.reducedMotion
    }
}
