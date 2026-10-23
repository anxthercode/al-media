import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Window
import ".."

ComboBox {
    id: control
    property string value: ""
    signal chosen(string value)
    readonly property bool menuVisible: popup.visible
    readonly property real menuHeight: popup.height
    function openMenu() { popup.open(); }
    implicitWidth: 160
    implicitHeight: 48
    textRole: "label"
    valueRole: "value"
    font.family: Theme.fontFamily
    font.pixelSize: 14
    hoverEnabled: true
    leftPadding: 14
    rightPadding: 36
    currentIndex: {
        const rows = model || [];
        for (let i = 0; i < rows.length; i++) if (String(rows[i].value) === value) return i;
        return rows.length ? 0 : -1;
    }
    onActivated: chosen(String(currentValue))
    contentItem: UiText { text: control.displayText; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; wrapMode: Text.NoWrap }
    indicator: UiIcon {
        name: "chevron"
        x: control.width - width - 14
        anchors.verticalCenter: parent.verticalCenter
        width: 16; height: 16
        rotation: control.popup.visible ? 180 : 0
        Behavior on rotation { NumberAnimation { duration: Theme.reducedMotion ? 0 : 180; easing.type: Easing.OutCubic } }
    }
    background: Rectangle {
        color: Theme.surface
        radius: 6
        border.color: control.visualFocus || control.popup.visible ? Theme.accent : control.hovered ? Theme.quiet : Theme.field
        Rectangle { anchors.fill: parent; anchors.margins: -4; color: "transparent"; radius: 8; border.color: Theme.accent; border.width: 2; visible: control.visualFocus }
    }
    delegate: ItemDelegate {
        required property var modelData
        required property int index
        width: control.width - 2
        height: 48
        highlighted: control.highlightedIndex === index
        contentItem: UiText { text: modelData.label; color: control.highlightedIndex === index ? Theme.accent : Theme.fg; verticalAlignment: Text.AlignVCenter; wrapMode: Text.NoWrap; elide: Text.ElideRight }
        background: Rectangle { color: control.highlightedIndex === index ? Theme.tint : Theme.surface3 }
    }
    popup: Popup {
        id: menu
        parent: control
        popupType: Popup.Item
        x: 0
        y: control.height
        onAboutToShow: {
            const overlay = Overlay.overlay;
            const origin = control.mapToItem(overlay, 0, 0);
            y = overlay && origin.y + control.height + implicitHeight > overlay.height - 8 ? -implicitHeight : control.height;
        }
        width: control.width
        implicitHeight: Math.min(300, control.count * 48 + 2)
        padding: 1
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
        contentItem: ListView {
            id: list
            acceptedButtons: Qt.NoButton
            clip: true
            implicitHeight: contentHeight
            model: menu.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator { }
        }
        background: Rectangle { color: Theme.surface3; border.color: Theme.field; radius: 6 }
    }
}
