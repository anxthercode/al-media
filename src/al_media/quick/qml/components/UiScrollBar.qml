import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Window
import ".."

ScrollBar {
    id: control
    property bool edge: false
    property Flickable scrollTarget: null
    property string upText: qsTr("Scroll up")
    property string downText: qsTr("Scroll down")
    readonly property bool expanded: barHover.hovered || pressed
    readonly property real arrowExtent: edge ? 18 : 0
    readonly property bool wheelAnimating: wheelAnimation.running
    property real wheelDirection: 0
    implicitWidth: edge ? 14 : 8
    padding: edge ? 0 : 1
    // Reserve the arrow space in both states: revealing arrows never moves the
    // thumb under the pointer or changes the drag coordinate system.
    topPadding: edge ? arrowExtent + 4 : 1
    bottomPadding: edge ? arrowExtent + 4 : 1
    hoverEnabled: true
    minimumSize: 0.08
    policy: ScrollBar.AsNeeded

    function stopRepeating() {
        for (let i = 0; i < arrows.count; ++i) {
            const arrow = arrows.itemAt(i);
            if (arrow) arrow.stopRepeating();
        }
    }
    function boundedOffset(offset) {
        const first = scrollTarget.originY - scrollTarget.topMargin;
        const last = Math.max(first, scrollTarget.originY + scrollTarget.contentHeight - scrollTarget.height + scrollTarget.bottomMargin);
        return Math.max(first, Math.min(last, offset));
    }
    function stopWheel() {
        wheelAnimation.stop();
        wheelDirection = 0;
    }
    function stopInteractions() {
        stopRepeating();
        stopWheel();
    }
    function scrollPixels(pixels) {
        stopWheel();
        if (scrollTarget) {
            // The Flickable owns its offset. Do not write a second, normalized
            // position while it is still applying wheel/flick movement.
            scrollTarget.cancelFlick();
            scrollTarget.contentY = boundedOffset(scrollTarget.contentY + pixels);
        } else {
            position = Math.max(0, Math.min(1 - size, position + pixels * size / Math.max(1, height)));
        }
    }
    function animateWheel(pixels) {
        if (!scrollTarget || Theme.reducedMotion) {
            scrollPixels(pixels);
            return;
        }
        // Accumulate rapid notches, but reverse from the visible position so an
        // old destination cannot pull the page against the next wheel gesture.
        const current = scrollTarget.contentY;
        const continuing = wheelAnimation.running && wheelDirection * pixels > 0;
        const destination = boundedOffset((continuing ? wheelAnimation.to : current) + pixels);
        stopWheel();
        scrollTarget.cancelFlick();
        if (Math.abs(destination - current) < 0.01) return;
        wheelDirection = pixels;
        wheelAnimation.from = current;
        wheelAnimation.to = destination;
        wheelAnimation.start();
    }
    function scrollWheel(wheel, pixelDevice = false) {
        stopRepeating();
        const wheelStep = Application.styleHints.wheelScrollLines * 24;
        // A touchpad can report a rounded zero-pixel frame with an angle delta.
        // Keep that frame still instead of treating it as a whole wheel notch.
        const pixels = pixelDevice || wheel.pixelDelta.y ? -wheel.pixelDelta.y : -wheel.angleDelta.y / 120 * wheelStep;
        if (pixelDevice || wheel.pixelDelta.y) {
            // Precise gestures follow the finger directly, including zero-delta
            // frames. They also interrupt a pending mouse-wheel animation.
            scrollPixels(pixels);
        } else if (pixels !== 0) animateWheel(pixels);
        wheel.accepted = true;
    }
    onPressedChanged: { if (pressed) stopInteractions(); }
    onVisibleChanged: { if (!visible) stopInteractions(); }
    onScrollTargetChanged: stopWheel()
    NumberAnimation {
        id: wheelAnimation
        target: control.scrollTarget
        property: "contentY"
        duration: 160
        easing.type: Easing.OutCubic
    }
    Connections {
        target: control.scrollTarget
        function onDraggingChanged() { if (target.dragging) control.stopWheel(); }
        function onContentHeightChanged() { control.stopWheel(); }
        function onHeightChanged() { control.stopWheel(); }
        function onOriginYChanged() { control.stopWheel(); }
        function onTopMarginChanged() { control.stopWheel(); }
        function onBottomMarginChanged() { control.stopWheel(); }
    }
    Connections {
        target: control.Window.window
        function onActiveChanged() { if (!target.active) control.stopInteractions(); }
        function onVisibilityChanged() { if (!target.visible || target.visibility === Window.Minimized) control.stopInteractions(); }
    }
    HoverHandler { id: barHover }
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.NoButton
        onWheel: wheel => control.scrollWheel(wheel)
    }
    contentItem: Item {
        implicitWidth: 6
        implicitHeight: 6
        Rectangle {
            objectName: "scrollThumb"
            anchors.right: parent.right
            anchors.rightMargin: control.edge ? 2 : 0
            width: control.expanded ? (control.edge ? 10 : 6) : 4
            height: parent.height
            radius: width / 2
            color: control.expanded ? Theme.quiet : Theme.field
            opacity: control.size < 1 ? 1 : 0
            Behavior on width { NumberAnimation { duration: Theme.motion; easing.type: Easing.OutCubic } }
            Behavior on color { ColorAnimation { duration: Theme.motion } }
        }
    }
    background: Item { }
    Repeater {
        id: arrows
        model: control.edge ? 2 : 0
        delegate: MouseArea {
            id: arrow
            required property int index
            readonly property int direction: index === 0 ? -1 : 1
            property bool repeatAllowed: false
            readonly property bool canMove: index === 0 ? control.position > 0.00001 : control.position < 1 - control.size - 0.00001
            z: 2
            objectName: index === 0 ? "scrollUp" : "scrollDown"
            width: control.width
            height: control.arrowExtent
            y: index === 0 ? 2 : parent.height - height - 2
            visible: control.size < 1 && control.expanded
            // Keep accepting the release at a boundary. Disabling the hit area
            // mid-press lets the underlying ScrollBar start its own interaction.
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton
            preventStealing: true
            Accessible.role: Accessible.Button
            Accessible.name: index === 0 ? control.upText : control.downText
            Accessible.onPressAction: { if (canMove) control.scrollPixels(direction * 40); }
            function stopRepeating() {
                repeatAllowed = false;
                if (delay) delay.stop();
                if (repeat) repeat.stop();
            }
            onPressed: {
                repeatAllowed = canMove;
                if (canMove) control.scrollPixels(direction * 40);
                if (canMove) delay.restart();
            }
            onReleased: stopRepeating()
            onCanceled: stopRepeating()
            onExited: stopRepeating()
            onCanMoveChanged: { if (!canMove) stopRepeating(); }
            onVisibleChanged: { if (!visible) stopRepeating(); }
            onWheel: wheel => control.scrollWheel(wheel)
            Timer {
                id: delay
                interval: 350
                onTriggered: { if (arrow.pressed && arrow.containsMouse && arrow.repeatAllowed) repeat.start(); }
            }
            Timer {
                id: repeat
                interval: 60
                repeat: true
                onTriggered: {
                    if (arrow.pressed && arrow.containsMouse && arrow.repeatAllowed && arrow.canMove)
                        control.scrollPixels(arrow.direction * 40);
                    else arrow.stopRepeating();
                }
            }
            Rectangle { anchors.fill: parent; radius: 3; color: arrow.pressed ? Theme.surface3 : arrow.containsMouse ? Theme.surface2 : "transparent" }
            UiIcon {
                name: "scrollArrow"
                anchors.centerIn: parent
                width: 10
                height: 8
                rotation: arrow.index === 0 ? 0 : 180
                tint: Theme.quiet
                opacity: arrow.canMove ? 1 : 0.35
            }
        }
    }
}
