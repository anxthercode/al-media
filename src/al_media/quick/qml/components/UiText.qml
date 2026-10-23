import QtQuick
import ".."

Text {
    font.family: Theme.fontFamily
    font.pixelSize: 14
    color: Theme.fg
    textFormat: Text.PlainText
    renderType: Text.NativeRendering
    wrapMode: Text.WordWrap
    lineHeightMode: Text.FixedHeight
    lineHeight: font.pixelSize * 1.45
    Accessible.role: Accessible.StaticText
    Accessible.name: text
}
