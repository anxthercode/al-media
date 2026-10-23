import QtQuick
import QtQuick.Controls.Basic
import ".."

FocusScope {
    id: control
    property string text: ""
    property string placeholderText: "00:00:00"
    property var units: ["Hours", "Minutes", "Seconds"]
    property bool hasError: false
    property int autoAdvanceTo: -1
    signal edited(string value)
    implicitWidth: 180
    implicitHeight: 44
    activeFocusOnTab: true
    clip: true

    // Keep the draft in the view model; focus and partial edits survive refreshes.
    function parts(value) {
        if (!value) return ["", "", ""];
        const values = value.replace(",", ".").split(":");
        while (values.length < 3) values.unshift("");
        return values;
    }
    function moveTo(index, automatic) {
        const field = segments.itemAt(Math.max(0, Math.min(2, index)));
        field.forceActiveFocus(Qt.OtherFocusReason);
        field.selectAll();
        autoAdvanceTo = automatic ? index : -1;
    }
    function update(index, value) {
        autoAdvanceTo = -1;
        // A pasted timestamp or compact MMSS/HHMMSS value also works.
        if (value.includes(":")) { edited(value); return; }
        if (index < 2 && /^\d{3,}$/.test(value)) {
            const digits = value.padStart(6, "0");
            edited(digits.slice(0, -4) + ":" + digits.slice(-4, -2) + ":" + digits.slice(-2));
            return;
        }
        const values = parts(text);
        values[index] = value;
        edited(values.every(v => v === "") ? "" : values.map(v => v || "0").join(":"));
        if (index < 2 && value.length === 2) moveTo(index + 1, true);
    }
    Rectangle {
        anchors.fill: parent
        radius: 6
        color: Theme.surface
        border.color: control.hasError ? Theme.error : control.activeFocus ? Theme.accent : hover.hovered ? Theme.quiet : Theme.field
        Behavior on border.color { ColorAnimation { duration: Theme.motion } }
    }
    HoverHandler { id: hover }
    Row {
        x: 14
        height: parent.height
        spacing: 0
        Repeater {
            id: segments
            model: 3
            TextField {
                id: segment
                required property int index
                objectName: control.objectName + ["Hours", "Minutes", "Seconds"][index]
                width: index === 2 ? Math.max(46, contentWidth + 8) : 28
                height: control.height
                focus: index === 0
                activeFocusOnTab: true
                text: {
                    const value = control.parts(control.text)[index];
                    if (!value || activeFocus) return value;
                    const digits = value.split(".");
                    digits[0] = digits[0].padStart(2, "0");
                    return digits.join(".");
                }
                placeholderText: control.parts(control.placeholderText)[index] || "00"
                font.family: Theme.fontFamily
                font.pixelSize: 14
                renderType: TextInput.NativeRendering
                color: Theme.fg
                placeholderTextColor: Theme.quiet
                selectionColor: Theme.accent
                selectedTextColor: "white"
                leftPadding: 0; rightPadding: index < 2 ? 8 : 0
                topPadding: 0; bottomPadding: 0
                horizontalAlignment: TextInput.AlignLeft
                verticalAlignment: TextInput.AlignVCenter
                selectByMouse: true
                inputMethodHints: Qt.ImhFormattedNumbersOnly
                validator: RegularExpressionValidator { regularExpression: /[0-9:.,]*/ }
                background: null
                Accessible.name: control.Accessible.name + ", " + control.units[index]
                ToolTip.visible: hovered
                ToolTip.text: control.units[index]
                ToolTip.delay: 500
                onTextEdited: control.update(index, text)
                onActiveFocusChanged: { if (activeFocus) { control.autoAdvanceTo = -1; selectAll(); } else deselect(); }
                Keys.onPressed: event => {
                    if (event.key === Qt.Key_Colon) {
                        // A manually typed colon after two digits must not skip
                        // the segment that automatic advance just selected.
                        if (control.autoAdvanceTo === index) control.autoAdvanceTo = -1;
                        else if (index < 2) control.moveTo(index + 1);
                        event.accepted = true;
                    }
                    else if (event.key === Qt.Key_Right && cursorPosition === text.length && index < 2) { control.moveTo(index + 1); event.accepted = true; }
                    else if ((event.key === Qt.Key_Left || event.key === Qt.Key_Backspace) && cursorPosition === 0 && index > 0) { control.moveTo(index - 1); event.accepted = true; }
                }
                UiText { visible: segment.index < 2; text: ":"; x: 21; anchors.verticalCenter: parent.verticalCenter; color: Theme.muted }
            }
        }
    }
    // Clicking the unused area still enters the control.
    TapHandler {
        onTapped: eventPoint => { if (eventPoint.position.x > 116) control.moveTo(2); }
    }
}
