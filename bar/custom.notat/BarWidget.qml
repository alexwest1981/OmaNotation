import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "custom.notat"

  readonly property string bin: Quickshell.env("HOME") + "/.local/bin/notat"
  readonly property string vaultDir: Quickshell.env("HOME") + "/Documents/OmaScribe Vault/Inspelningar"
  readonly property color fg: root.bar ? root.bar.foreground : Color.foreground
  readonly property color recColor: "#f87171"
  readonly property color dimFg: Qt.darker(root.fg, 1.35)

  property bool recording: false
  property bool busy: false          // notat jobbar (startar/transkriberar)
  property int seconds: 0
  property bool popupOpen: false
  property var enheter: []           // [{typ, nod, talare, beskrivning, vald}]
  property var modeller: []          // [{id, namn, mb, beskrivning, finns, vald}]
  property string nedladdning: ""    // id som laddas ner just nu
  property int nedladdningProcent: 0
  property string felText: ""

  readonly property string clock:
    Math.floor(seconds / 60).toString().padStart(2, "0") + ":" +
    (seconds % 60).toString().padStart(2, "0")

  readonly property string modellNamn: {
    for (var i = 0; i < root.modeller.length; i++)
      if (root.modeller[i].vald) return root.modeller[i].id
    return ""
  }

  implicitWidth: contentRow.implicitWidth + Style.space(14)
  implicitHeight: barSize

  // Hjälper felsökning: syns i journalen (journalctl --user -f | grep notat) när widgeten laddas
  Component.onCompleted: console.log("notat: bar-widget laddad")

  function refresh() {
    if (!statusProc.running) statusProc.running = true
  }

  function hamtaEnheter() {
    if (!devProc.running) devProc.running = true
  }

  function hamtaModeller() {
    if (!modellProc.running) modellProc.running = true
  }

  function oppnaPopup() {
    root.felText = ""
    root.popupOpen = true
    root.hamtaEnheter()
    root.hamtaModeller()
  }

  function valj(nod) {
    valjProc.command = [root.bin, "valj", nod]
    valjProc.running = true
  }

  // Finns modellen: byt till den. Saknas den: ladda ner den (en i taget).
  function valjModell(m) {
    if (m.finns) {
      modellValProc.command = [root.bin, "modell", m.id]
      modellValProc.running = true
    } else if (root.nedladdning === "") {
      root.felText = ""
      root.nedladdning = m.id
      root.nedladdningProcent = 0
      hamtaProc.command = [root.bin, "hamta", m.id]
      hamtaProc.running = true
    }
  }

  function toggle() {
    if (root.busy) return
    root.busy = true
    toggleProc.running = false
    toggleProc.running = true
  }

  function tooltip() {
    var modell = root.modellNamn ? " · " + root.modellNamn : ""
    if (root.busy) return "Notat jobbar (transkriberar) …"
    if (root.recording) return "Spelar in " + root.clock + modell + " — klick stoppar och gör dokument. Högerklick: källor och modell."
    return "Klick: anteckna mötet/föreläsningen" + modell + ". Högerklick: välj källor och modell."
  }

  Process {
    id: statusProc
    command: [root.bin, "status", "--json"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var d = JSON.parse(text.trim())
          root.recording = d.recording === true
          root.seconds = d.seconds || 0
        } catch (e) {
          root.recording = false
        }
      }
    }
  }

  Process {
    id: toggleProc
    command: [root.bin]
    onExited: function (code) {
      root.busy = false
      root.refresh()
    }
  }

  Process {
    id: devProc
    command: [root.bin, "devices"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          root.enheter = JSON.parse(text.trim()).enheter || []
        } catch (e) {
          root.felText = "kunde inte läsa enhetslistan"
        }
      }
    }
  }

  Process {
    id: valjProc
    // command sätts i valj() innan running
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var svar = JSON.parse(text.trim())
          if (svar.ok === false) root.felText = svar.error || "kunde inte ändra"
        } catch (e) {
          root.felText = "oväntat svar från notat valj"
        }
      }
    }
    onExited: function (code) {
      root.hamtaEnheter()
    }
  }

  Process {
    id: allaProc
    command: [root.bin, "valj", "alla"]
    onExited: function (code) {
      root.hamtaEnheter()
    }
  }

  Process {
    id: modellProc
    command: [root.bin, "modeller"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          root.modeller = JSON.parse(text.trim()).modeller || []
        } catch (e) {
          root.felText = "kunde inte läsa modellistan"
        }
      }
    }
  }

  Process {
    id: modellValProc
    // command sätts i valjModell() innan running
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var svar = JSON.parse(text.trim())
          if (svar.ok === false) root.felText = svar.error || "kunde inte byta modell"
        } catch (e) {
          root.felText = "oväntat svar från notat modell"
        }
      }
    }
    onExited: function (code) {
      root.hamtaModeller()
    }
  }

  Process {
    id: hamtaProc
    // command sätts i valjModell() innan running
    stdout: SplitParser {
      onRead: function (line) {
        try {
          var d = JSON.parse(String(line).trim())
          if (d.procent !== undefined) root.nedladdningProcent = d.procent
          if (d.ok === false) root.felText = d.error || "nedladdningen misslyckades"
        } catch (e) {
        }
      }
    }
    stderr: SplitParser {
      onRead: function (line) {
        if (String(line).trim().length > 0) root.felText = String(line).trim()
      }
    }
    onExited: function (code) {
      root.nedladdning = ""
      root.nedladdningProcent = 0
      root.hamtaModeller()
    }
  }

  Process {
    id: openVaultProc
    command: ["xdg-open", root.vaultDir]
  }

  Timer {
    interval: 1000
    repeat: true
    running: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  Row {
    id: contentRow
    anchors.centerIn: parent
    spacing: Style.space(5)

    Rectangle {
      id: dot
      width: Style.spaceReal(7)
      height: Style.spaceReal(7)
      radius: width / 2
      color: root.recColor
      visible: root.recording || root.busy
      anchors.verticalCenter: parent.verticalCenter

      SequentialAnimation on opacity {
        running: root.recording
        loops: Animation.Infinite
        NumberAnimation { to: 0.25; duration: 600 }
        NumberAnimation { to: 1.0; duration: 600 }
      }
    }

    Text {
      text: String.fromCodePoint(0xF130)
      color: root.recording ? root.recColor : root.fg
      font.family: root.bar ? root.bar.fontFamily : Style.font.family
      font.pixelSize: Style.font.title
      anchors.verticalCenter: parent.verticalCenter

      Behavior on color {
        ColorAnimation { duration: 250 }
      }
    }

    Text {
      visible: root.recording || root.busy
      text: root.busy ? "…" : root.clock
      color: root.recording ? root.recColor : root.fg
      font.family: root.bar ? root.bar.fontFamily : Style.font.family
      font.pixelSize: Style.font.bodySmall
      font.bold: true
      anchors.verticalCenter: parent.verticalCenter
    }
  }

  MouseArea {
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    acceptedButtons: Qt.LeftButton | Qt.RightButton
    onEntered: if (root.bar) root.bar.showTooltip(root, root.tooltip())
    onExited: if (root.bar) root.bar.hideTooltip(root)
    onClicked: function (mouse) {
      if (mouse.button === Qt.RightButton) {
        if (root.popupOpen) root.popupOpen = false
        else root.oppnaPopup()
      } else if (root.popupOpen) {
        root.popupOpen = false
      } else {
        root.toggle()
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Källor och modell (skrivs till notat config via kommandoraden)
  // ---------------------------------------------------------------------------
  PopupCard {
    id: popup
    anchorItem: root
    bar: root.bar
    owner: root
    open: root.popupOpen
    contentWidth: popup.fittedContentWidth(Style.space(450))
    contentHeight: popup.fittedContentHeight(popCol.implicitHeight)

    Column {
      id: popCol
      anchors.fill: parent
      spacing: Style.space(8)

      Text {
        text: "Källor att spela in"
        color: root.fg
        font.family: root.bar ? root.bar.fontFamily : Style.font.family
        font.pixelSize: Style.font.subtitle
        font.bold: true
      }

      Text {
        width: popCol.width
        text: root.recording
              ? "Inspelningen rullar — ändringen gäller nästa gång"
              : "Klicka på en enhet för att slå av eller på den"
        color: root.dimFg
        font.family: root.bar ? root.bar.fontFamily : Style.font.family
        font.pixelSize: Style.font.caption
        wrapMode: Text.WordWrap
      }

      Repeater {
        model: root.enheter

        delegate: Rectangle {
          required property var modelData

          width: popCol.width
          height: Style.space(36)
          radius: Style.spacing.labelGap
          color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, modelData.vald ? 0.10 : 0.03)
          border.width: 1
          border.color: modelData.vald
                        ? Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.55)
                        : Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.12)

          Row {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: Style.space(8)
            spacing: Style.space(8)

            Rectangle {
              width: Style.spaceReal(12)
              height: Style.spaceReal(12)
              radius: Style.spaceReal(3)
              anchors.verticalCenter: parent.verticalCenter
              color: modelData.vald ? Color.accent : "transparent"
              border.width: 1
              border.color: modelData.vald ? Color.accent : root.dimFg
            }

            Text {
              width: popCol.width - Style.space(115)
              anchors.verticalCenter: parent.verticalCenter
              text: modelData.beskrivning
              color: modelData.vald ? root.fg : root.dimFg
              elide: Text.ElideRight
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.pixelSize: Style.font.bodySmall
            }

            Text {
              anchors.verticalCenter: parent.verticalCenter
              text: modelData.typ === "ut" ? "utgång" : "mikrofon"
              color: root.dimFg
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.pixelSize: Style.font.caption
            }
          }

          MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.valj(modelData.nod)
          }
        }
      }

      Rectangle {
        width: popCol.width
        height: 1
        color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.15)
      }

      Text {
        text: "Modell"
        color: root.fg
        font.family: root.bar ? root.bar.fontFamily : Style.font.family
        font.pixelSize: Style.font.subtitle
        font.bold: true
      }

      Text {
        width: popCol.width
        text: root.nedladdning !== ""
              ? "Laddar ner " + root.nedladdning + " — " + root.nedladdningProcent + " %"
              : "Klicka för att byta. Saknas modellen laddas den ner först."
        color: root.nedladdning !== "" ? Color.accent : root.dimFg
        font.family: root.bar ? root.bar.fontFamily : Style.font.family
        font.pixelSize: Style.font.caption
        wrapMode: Text.WordWrap
      }

      Repeater {
        model: root.modeller

        delegate: Rectangle {
          required property var modelData

          width: popCol.width
          height: Style.space(42)
          radius: Style.spacing.labelGap
          color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, modelData.vald ? 0.10 : 0.03)
          border.width: 1
          border.color: modelData.vald
                        ? Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.55)
                        : Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.12)

          Column {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: Style.space(8)
            anchors.rightMargin: Style.space(8)
            spacing: Style.space(1)

            Row {
              spacing: Style.space(8)

              Rectangle {
                width: Style.spaceReal(12)
                height: Style.spaceReal(12)
                radius: Style.spaceReal(3)
                anchors.verticalCenter: parent.verticalCenter
                color: modelData.vald ? Color.accent : "transparent"
                border.width: 1
                border.color: modelData.vald ? Color.accent : root.dimFg
              }

              Text {
                width: popCol.width - Style.space(200)
                anchors.verticalCenter: parent.verticalCenter
                text: modelData.namn
                color: modelData.vald ? root.fg : (modelData.finns ? root.fg : root.dimFg)
                elide: Text.ElideRight
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.bodySmall
              }

              Text {
                anchors.verticalCenter: parent.verticalCenter
                text: root.nedladdning === modelData.id
                      ? root.nedladdningProcent + " %"
                      : (modelData.vald ? "vald"
                         : (modelData.finns ? "välj" : "ladda ner " + modelData.mb + " MB"))
                color: modelData.vald ? Color.accent : root.dimFg
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
                font.bold: modelData.vald
              }
            }

            Text {
              width: parent.width
              text: modelData.beskrivning
              color: root.dimFg
              elide: Text.ElideRight
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.pixelSize: Style.font.caption
            }
          }

          // nedladdningsmätare
          Rectangle {
            visible: root.nedladdning === modelData.id
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            height: Style.spaceReal(3)
            width: parent.width * root.nedladdningProcent / 100
            color: Color.accent
          }

          MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            enabled: root.nedladdning === "" || root.nedladdning === modelData.id
            cursorShape: Qt.PointingHandCursor
            onClicked: root.valjModell(modelData)
          }
        }
      }

      Text {
        visible: root.felText.length > 0
        width: popCol.width
        text: root.felText
        color: root.recColor
        wrapMode: Text.WordWrap
        font.family: root.bar ? root.bar.fontFamily : Style.font.family
        font.pixelSize: Style.font.caption
      }

      Row {
        spacing: Style.space(6)

        WidgetButton {
          bar: root.bar
          fixedHeight: Style.space(30)
          text: "Slå på alla"
          tooltipText: "Spela in samtliga enheter igen"
          onPressed: function () { allaProc.running = true }
        }

        WidgetButton {
          bar: root.bar
          fixedHeight: Style.space(30)
          text: "Uppdatera"
          tooltipText: "Läs enhets- och modellistan på nytt"
          onPressed: function () { root.hamtaEnheter(); root.hamtaModeller() }
        }

        WidgetButton {
          bar: root.bar
          fixedHeight: Style.space(30)
          text: "Öppna mappen"
          tooltipText: "Öppna mappen med dokumenten"
          onPressed: function () { openVaultProc.running = true }
        }
      }
    }
  }
}
