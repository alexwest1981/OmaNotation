import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "io.github.alexwest1981.omanotation"

  readonly property string bin: Quickshell.env("HOME") + "/.local/bin/notat"
  // The CLI decides where the documents are (it keeps a pre-1.1.1 Inspelningar/ folder if one
  // exists), so the folder is read from `notat devices` and this is only the first guess.
  property string vaultDir: Quickshell.env("HOME") + "/Documents/OmaScribe Vault/Recordings"
  readonly property color fg: root.bar ? root.bar.foreground : Color.foreground
  readonly property color recColor: "#f87171"
  readonly property color dimFg: Qt.darker(root.fg, 1.35)

  property bool recording: false
  property bool busy: false          // notat is transcribing (read from notat status)
  property int seconds: 0            // length of the recording
  property int jobSeconds: 0         // length of the transcription
  property bool popupOpen: false
  property var enheter: []           // [{kind, node, speaker, description, selected}]
  property var modeller: []          // [{id, name, mb, description, downloaded, selected}]
  property var roster: ({})          // {on, downloaded, threshold, speaker_count}
  property string nedladdning: ""    // id currently being downloaded
  property int nedladdningProcent: 0
  property string felText: ""
  // The bar's tooltip only considers a target that answers `tooltipHovered`
  // (Bar.targetTooltipHovered). Without it showTooltip() returns early and the
  // tooltip texts below could never be seen.
  readonly property bool tooltipHovered: mouseArea.containsMouse

  function mmss(s) {
    return Math.floor(s / 60).toString().padStart(2, "0") + ":" +
           (s % 60).toString().padStart(2, "0")
  }

  // The clock shows the recording while it runs, otherwise how long the job has been going.
  readonly property string clock: root.mmss(root.recording ? root.seconds : root.jobSeconds)

  readonly property string modellNamn: {
    for (var i = 0; i < root.modeller.length; i++)
      if (root.modeller[i].selected) return root.modeller[i].id
    return ""
  }

  implicitWidth: contentRow.implicitWidth + Style.space(14)
  implicitHeight: barSize

  // Helps debugging: shows in the journal (journalctl --user -f | grep notat) when the widget loads
  Component.onCompleted: console.log("notat: bar widget loaded")

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
    valjProc.command = [root.bin, "select", nod]
    valjProc.running = true
  }

  // If the model is there: switch to it. If it is missing: download it (one at a time).
  function valjModell(m) {
    if (m.downloaded) {
      modellValProc.command = [root.bin, "model", m.id]
      modellValProc.running = true
    } else if (root.nedladdning === "") {
      root.felText = ""
      root.nedladdning = m.id
      root.nedladdningProcent = 0
      hamtaProc.command = [root.bin, "download", m.id]
      hamtaProc.running = true
    }
  }

  // Speaker separation: a toggle when the models are there, otherwise they are downloaded first
  function vaxlaRoster() {
    if (root.roster.downloaded === true) {
      rosterProc.command = [root.bin, "speakers", root.roster.on === true ? "off" : "on"]
      rosterProc.running = true
    } else if (root.nedladdning === "") {
      root.felText = ""
      root.nedladdning = "speaker separation"
      root.nedladdningProcent = 0
      hamtaProc.command = [root.bin, "speakers", "fetch"]
      hamtaProc.running = true
    }
  }

  // PopupCard.close() hands the dismissal back to the owner when the owner has
  // a `close` method (PopupCard.qml:73). The focus grab calls it whenever you
  // click outside, so without this method PopupCard falls through to
  // `root.open = false` — an imperative write that destroys the
  // `open: root.popupOpen` binding and leaves popupOpen stuck true: the menu
  // never opens again and the first click on the icon is eaten clearing the
  // stale flag.
  function close() {
    root.popupOpen = false
  }

  function toggle() {
    if (root.busy) return
    root.busy = true
    toggleProc.running = false
    toggleProc.running = true
  }

  function tooltip() {
    var modell = root.modellNamn ? " · " + root.modellNamn : ""
    var voice = root.roster.on === true ? " · voices" : ""
    if (root.busy) return "Notat is transcribing " + root.clock + modell + voice +
                          " — the document comes when it is done. Right-click: sources, model and voices."
    if (root.recording) return "Recording " + root.clock + modell + voice + " — a click stops and makes the document. Right-click: sources, model and voices."
    return "Click: take notes of the meeting/lecture" + modell + voice + ". Right-click: choose sources, model and voices."
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
          // The job lives in notat (job file), not in the widget: reloading the
          // plugin must not make the transcription look finished.
          root.busy = d.transcribing === true
          root.jobSeconds = d.transcribing_seconds || 0
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
          var d = JSON.parse(text.trim())
          root.enheter = d.devices || []
          root.roster = d.speakers || ({})
          if (d.vault) root.vaultDir = d.vault
        } catch (e) {
          root.felText = "could not read the device list"
        }
      }
    }
  }

  Process {
    id: rosterProc
    // command is set in vaxlaRoster() before running
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var svar = JSON.parse(text.trim())
          if (svar.ok === false) root.felText = svar.error || "could not change it"
        } catch (e) {
          root.felText = "unexpected response from notat speakers"
        }
      }
    }
    onExited: function (code) {
      root.hamtaEnheter()
    }
  }

  Process {
    id: valjProc
    // command is set in valj() before running
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var svar = JSON.parse(text.trim())
          if (svar.ok === false) root.felText = svar.error || "could not change it"
        } catch (e) {
          root.felText = "unexpected response from notat select"
        }
      }
    }
    onExited: function (code) {
      root.hamtaEnheter()
    }
  }

  Process {
    id: allaProc
    command: [root.bin, "select", "all"]
    onExited: function (code) {
      root.hamtaEnheter()
    }
  }

  Process {
    id: modellProc
    command: [root.bin, "models"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          root.modeller = JSON.parse(text.trim()).models || []
        } catch (e) {
          root.felText = "could not read the model list"
        }
      }
    }
  }

  Process {
    id: modellValProc
    // command is set in valjModell() before running
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var svar = JSON.parse(text.trim())
          if (svar.ok === false) root.felText = svar.error || "could not switch model"
        } catch (e) {
          root.felText = "unexpected response from notat model"
        }
      }
    }
    onExited: function (code) {
      root.hamtaModeller()
    }
  }

  Process {
    id: hamtaProc
    // command is set in valjModell() before running
    stdout: SplitParser {
      onRead: function (line) {
        try {
          var d = JSON.parse(String(line).trim())
          if (d.percent !== undefined) root.nedladdningProcent = d.percent
          if (d.ok === false) root.felText = d.error || "the download failed"
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
      text: root.clock
      color: root.recording ? root.recColor : root.fg
      font.family: root.bar ? root.bar.fontFamily : Style.font.family
      font.pixelSize: Style.font.bodySmall
      font.bold: true
      anchors.verticalCenter: parent.verticalCenter
    }
  }

  MouseArea {
    id: mouseArea
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    acceptedButtons: Qt.LeftButton | Qt.RightButton
    onEntered: if (root.bar) root.bar.showTooltip(root, root.tooltip())
    onExited: if (root.bar) root.bar.hideTooltip(root)
    onClicked: function (mouse) {
      if (mouse.button === Qt.RightButton) {
        // Trace in the journal (journalctl --user | grep notat): a right-click
        // that does not open the menu must be distinguishable from a click that
        // never arrived at the widget.
        console.log("notat: right-click -> " + (root.popupOpen ? "close" : "open"))
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
  // Sources and model (written to notat config via the command line)
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
        text: "Sources to record"
        color: root.fg
        font.family: root.bar ? root.bar.fontFamily : Style.font.family
        font.pixelSize: Style.font.subtitle
        font.bold: true
      }

      Text {
        width: popCol.width
        text: root.recording
              ? "The recording is running — the change applies next time"
              : "Click a device to turn it off or on"
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
          color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, modelData.selected ? 0.10 : 0.03)
          border.width: 1
          border.color: modelData.selected
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
              color: modelData.selected ? Color.accent : "transparent"
              border.width: 1
              border.color: modelData.selected ? Color.accent : root.dimFg
            }

            Text {
              width: popCol.width - Style.space(115)
              anchors.verticalCenter: parent.verticalCenter
              text: modelData.description
              color: modelData.selected ? root.fg : root.dimFg
              elide: Text.ElideRight
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.pixelSize: Style.font.bodySmall
            }

            Text {
              anchors.verticalCenter: parent.verticalCenter
              text: modelData.kind === "out" ? "output" : "microphone"
              color: root.dimFg
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.pixelSize: Style.font.caption
            }
          }

          MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.valj(modelData.node)
          }
        }
      }

      Rectangle {
        width: popCol.width
        height: 1
        color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.15)
      }

      Text {
        text: "Model"
        color: root.fg
        font.family: root.bar ? root.bar.fontFamily : Style.font.family
        font.pixelSize: Style.font.subtitle
        font.bold: true
      }

      Text {
        width: popCol.width
        text: "Click to switch. If the model is missing it is downloaded first."
        color: root.dimFg
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
          color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, modelData.selected ? 0.10 : 0.03)
          border.width: 1
          border.color: modelData.selected
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
                color: modelData.selected ? Color.accent : "transparent"
                border.width: 1
                border.color: modelData.selected ? Color.accent : root.dimFg
              }

              Text {
                width: popCol.width - Style.space(200)
                anchors.verticalCenter: parent.verticalCenter
                text: modelData.name
                color: modelData.selected ? root.fg : (modelData.downloaded ? root.fg : root.dimFg)
                elide: Text.ElideRight
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.bodySmall
              }

              Text {
                anchors.verticalCenter: parent.verticalCenter
                text: root.nedladdning === modelData.id
                      ? root.nedladdningProcent + " %"
                      : (modelData.selected ? "selected"
                         : (modelData.downloaded ? "choose" : "download " + modelData.mb + " MB"))
                color: modelData.selected ? Color.accent : root.dimFg
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
                font.bold: modelData.selected
              }
            }

            Text {
              width: parent.width
              text: modelData.description
              color: root.dimFg
              elide: Text.ElideRight
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.pixelSize: Style.font.caption
            }
          }

          // download progress bar
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

      Rectangle {
        width: popCol.width
        height: 1
        color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.15)
      }

      Text {
        text: "Voices"
        color: root.fg
        font.family: root.bar ? root.bar.fontFamily : Style.font.family
        font.pixelSize: Style.font.subtitle
        font.bold: true
      }

      Text {
        width: popCol.width
        text: "The voices in the meeting get their own names (Speaker 1, 2 …) instead of a single \"Meeting\". "
              + "Your own microphone is always \"You\". Costs extra time: about a fifth of the recording's length."
        color: root.dimFg
        font.family: root.bar ? root.bar.fontFamily : Style.font.family
        font.pixelSize: Style.font.caption
        wrapMode: Text.WordWrap
      }

      Rectangle {
        width: popCol.width
        height: Style.space(42)
        radius: Style.spacing.labelGap
        color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, root.roster.on ? 0.10 : 0.03)
        border.width: 1
        border.color: root.roster.on
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
              color: root.roster.on ? Color.accent : "transparent"
              border.width: 1
              border.color: root.roster.on ? Color.accent : root.dimFg
            }

            Text {
              width: popCol.width - Style.space(200)
              anchors.verticalCenter: parent.verticalCenter
              text: "Separate voices"
              color: root.fg
              elide: Text.ElideRight
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.pixelSize: Style.font.bodySmall
            }

            Text {
              anchors.verticalCenter: parent.verticalCenter
              text: root.roster.downloaded !== true
                    ? "download 70 MB"
                    : (root.roster.on === true ? "on" : "off")
              color: root.roster.on ? Color.accent : root.dimFg
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.pixelSize: Style.font.caption
              font.bold: root.roster.on === true
            }
          }

          Text {
            width: parent.width
            text: root.roster.downloaded !== true
                  ? "sherpa-onnx + voice models (no cloud service)"
                  : ("speaker count: " + (root.roster.speaker_count > 0
                     ? root.roster.speaker_count + " (fixed)"
                     : "detected automatically"))
            color: root.dimFg
            elide: Text.ElideRight
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.pixelSize: Style.font.caption
          }
        }

        Rectangle {
          visible: root.nedladdning === "speaker separation"
          anchors.left: parent.left
          anchors.bottom: parent.bottom
          height: Style.spaceReal(3)
          width: parent.width * root.nedladdningProcent / 100
          color: Color.accent
        }

        MouseArea {
          anchors.fill: parent
          hoverEnabled: true
          enabled: root.nedladdning === "" || root.nedladdning === "speaker separation"
          cursorShape: Qt.PointingHandCursor
          onClicked: root.vaxlaRoster()
        }
      }

      Text {
        visible: root.nedladdning !== ""
        width: popCol.width
        text: "Downloading " + (root.nedladdning === "speaker separation"
              ? "the speaker separation (~70 MB)" : root.nedladdning)
              + (root.nedladdningProcent > 0 ? " — " + root.nedladdningProcent + " %" : " …")
        color: Color.accent
        wrapMode: Text.WordWrap
        font.family: root.bar ? root.bar.fontFamily : Style.font.family
        font.pixelSize: Style.font.caption
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
          text: "Turn on all"
          tooltipText: "Record all devices again"
          onPressed: function () { allaProc.running = true }
        }

        WidgetButton {
          bar: root.bar
          fixedHeight: Style.space(30)
          text: "Refresh"
          tooltipText: "Read the device and model list again"
          onPressed: function () { root.hamtaEnheter(); root.hamtaModeller() }
        }

        WidgetButton {
          bar: root.bar
          fixedHeight: Style.space(30)
          text: "Open folder"
          tooltipText: "Open the folder with the documents"
          onPressed: function () { openVaultProc.running = true }
        }
      }
    }
  }
}
