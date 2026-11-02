import QtQuick

WheelHandler {
    required property UiScrollBar scrollBar
    target: null
    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
    // Use one bounded offset path for mouse, pixel-based touchpads and the bar.
    // Accepting the event here avoids a second movement by Flickable itself.
    onWheel: event => scrollBar.scrollWheel(event, point.device && point.device.type === PointerDevice.TouchPad)
}
