import QtQuick
import QtQuick.Window
import ".."

Image {
    property string name: "download"
    property color tint: Theme.muted
    width: 20
    height: 20
    source: "image://icons/" + name + "/" + String(tint).slice(-6)
    sourceSize.width: Math.round(width * Screen.devicePixelRatio)
    sourceSize.height: Math.round(height * Screen.devicePixelRatio)
    fillMode: Image.PreserveAspectFit
    smooth: true
    Accessible.ignored: true
}
