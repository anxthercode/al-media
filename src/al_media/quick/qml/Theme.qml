pragma Singleton
import QtQuick

QtObject {
    property bool light: false
    property bool reducedMotion: false
    property string fontFamily: "Segoe UI"
    readonly property int motion: reducedMotion ? 0 : 140
    readonly property color bg: light ? "#f8f8fb" : "#0c0c0e"
    readonly property color surface: light ? "#ffffff" : "#111114"
    readonly property color surface2: light ? "#f1f1f7" : "#17171b"
    readonly property color surface3: light ? "#e0e0e8" : "#1e1e24"
    readonly property color fg: light ? "#1c1c23" : "#eaeaf2"
    readonly property color muted: light ? "#4b4b60" : "#a8a8be"
    readonly property color quiet: light ? "#56566c" : "#85859a"
    readonly property color border: light ? "#cacad2" : "#222228"
    readonly property color field: light ? "#a5a5b0" : "#2c2c35"
    readonly property color accent: light ? "#2853cd" : "#4f7ef8"
    readonly property color primary: light ? "#123bb5" : "#3968df"
    readonly property color primaryHover: light ? "#002c9f" : "#2c5bd2"
    readonly property color tint: light ? "#102853cd" : "#1a4f7ef8"
    readonly property color navBorder: light ? "#382853cd" : "#384f7ef8"
    readonly property color error: light ? "#a1272c" : "#e05c5c"
    readonly property color success: light ? "#187d45" : "#3ec97a"
    readonly property color warning: light ? "#815c08" : "#d4a030"
}
