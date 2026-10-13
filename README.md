# OmaNotation (command: `notat`)

Meeting and lecture note taker for Linux/Omarchy. It records **both audio sides** (the meeting
from each output's monitor, you from the microphones), transcribes with whisper.cpp and writes a
markdown document when you stop. A button in the Omarchy bar starts and stops it; right-click
picks sources, model and downloads.

![A meeting room with the notes OmaNotation writes](meeting-notes.jpg)

(The images in this repository are illustrations, not screenshots of the widget.)

## Installation

Omarchy puts the bar widget in `~/.config/omarchy/plugins/<id>` with `omarchy plugin add`, but the
`notat` command, the models and the VAD model are installed by `install.sh` — which is why the
listing is *Manual setup*:

```bash
omarchy plugin add https://github.com/alexwest1981/OmaNotation.git --enable
~/.config/omarchy/plugins/io.github.alexwest1981.omanotation/install.sh
```

Anywhere else (any Linux): clone the repository and run `install.sh` — it links the command into
`~/.local/bin/notat`, downloads the VAD model and one whisper model, and installs the bar widget
if Omarchy is present:

```bash
git clone https://github.com/alexwest1981/OmaNotation.git
cd OmaNotation
./install.sh                       # command + VAD model + kb-whisper-small + bar widget
./install.sh --ingen-modell        # if you already have a model
```

The plugin lives in the repository root (`manifest.json` + `BarWidget.qml`), the layout the
Omarchy plugin marketplace requires. `install.sh` does not copy into a plugin folder that Omarchy
fetched itself (that folder is under git and is updated with
`omarchy plugin update io.github.alexwest1981.omanotation`).

Requires `python3` (stdlib only), `ffmpeg`, PipeWire (`pactl`) and `whisper-cli` in `PATH` — build
whisper.cpp for your machine following
[its own build documentation](https://github.com/ggml-org/whisper.cpp) and put `whisper-cli` in
`~/.local/bin`. The CUDA flag (`-DGGML_CUDA=ON`) is what the speed table below measures: 26×
realtime on an RTX 3060 Ti, against roughly 1× on CPU.

## Usage

| Command | What it does |
|---|---|
| `notat` | starts if nothing is recording, otherwise stops + transcribes |
| `notat start` / `notat stop` | the same thing, explicitly |
| `notat stop --wait` | wait for the document instead of handing the job off |
| `notat status [--json]` | the state (the bar polls this) |
| `notat devices` | devices, model and vault in use |
| `notat valj <device>` | toggle a device on/off (`notat valj alla` = everything on) |
| `notat modeller` | the models, which one is selected and which are downloaded |
| `notat modell <id>` | switch model |
| `notat hamta <id>` | download a model (one percentage per line) |
| `notat röster på\|av` | separate the speakers in the document (Deltagare 1, 2 …) |
| `notat diar-hamta` | download the speaker separation (~70 MB) |
| `notat transcribe <dir>` | redo an earlier recording (e.g. with a better model) |
| `notat möte "Title"` | name the meeting and set participants (see below) |
| `notat namn` | known voices: show, toggle, save a voice from a file |
| `notat glöm <Name>` | delete a voice profile |
| `notat sök <word>` | search the meeting documents (ripgrep over the vault) |
| `notat senaste [--öppna]` | the path to the most recently written document |
| `notat stop --no-summary` | skip the AI summary |

**The bar button** (`io.github.alexwest1981.omanotation`, the microphone icon): left click starts
and stops and shows a counter. **Right click** opens the menu in three sections: **Sources to
record** (toggle devices), **Model** (switch model, the download runs by itself if one is
missing) and **Voices** (separate the speakers). A click outside closes the menu. Menu changes
apply to the next recording — a running recording is left alone.

The stop answers immediately: the transcription runs in **its own child process in its own
session**, not as a child of the bar widget. A reload of the plugin (theme, edited neighbour,
`omarchy-restart-shell`) kills children of the widget — and did so in the middle of a job: a
29-minute recording never became a document. The child writes
`$XDG_RUNTIME_DIR/notat/transcription.json`, and that is the file the bar reads: the counter
stays at **transcribing mm:ss** until the document exists. `notat stop --wait` waits instead (for
scripts and tests).

## Where it listens

**Every** audio output (their monitor: everything that is played — Zoom, video, music) and
**every** audio input (microphones, line-in). One ffmpeg per device, one file per device, so a
device that dies (unplugged USB, busy HDMI) does not take the others down.

The same audio captured by several devices is merged by **comparing the audio, not the text**
(whisper writes different words for the same sentence depending on which microphone heard it —
measured 0.4 in text similarity for the same second). The envelopes are compared with correlation
and a delay search, and the strongest copy is kept.

Paragraph boundaries drift a few seconds between devices — whisper places the same sentence at,
say, 46–48 s on one track and 48–52 s on the other (measured). Pairs are therefore matched by
**closeness in time**, and the comparison is made against the other device's audio at the *same*
moment: 0.99 for the same sentence, against 0.57 with the old comparison where the duplicate got
through. Comparing a shared window instead does not work — if both tracks carry the same audio,
any window correlates (measured 0.99 even for two paragraphs 20 seconds apart), so the whole
meeting would be merged into one paragraph.

**Loudspeakers produce duplicates no heuristic can remove.** If the microphone hears the meeting
through the room, the microphone's audio is not a copy of the output but a mix (your voice + the
meeting), and then the discussion appears twice. The document gets a warning about it, with
numbers:

> [!warning] Mötets ljud hördes i rummet (1 av 2 mikrofonstycken är samma ljud som utgången) …

Headphones (or echo cancellation in the meeting app) give clean text. Measured: microphone
against output sits at 0.64–0.70 in correlation when the audio is heard in the room, while
different audio at the same time stays below 0.3.

If you would rather control it exactly: `NOTAT_SINK`/`NOTAT_SOURCE` lock the recording to two
devices.

## Models (measured, not guessed)

The whisper models are picked in the bar menu or with `notat modell <id>`. The catalogue contains
KBLab's Swedish-trained **KB-Whisper** and OpenAI's multilingual models. Measured on two Swedish
samples with known text (272 and 342 words, `tools/jamfor.py`) on an RTX 3060 Ti:

| Model | Size | Sample 1 (119 s) | Sample 2 (143 s) | Speed |
|---|---|---|---|---|
| **kb-whisper-small** | 466 MB | **4.2 %** | 5.0 % | 26× realtime |
| kb-whisper-medium | 1.5 GB | 4.6 % | — | 18× |
| kb-whisper-large-q5 | 1.1 GB | 6.5 % | — | 8× |
| kb-whisper-large | 2.9 GB | 6.9 % | **3.8 %** | 11× |
| openai-small | 466 MB | 8.0 % | 6.7 % | 25× |

How to read it: the Swedish-trained KB-Whisper models beat OpenAI small on both samples, and
small/large sit close together and **swap places depending on the material** — small is the
default for speed (26× against 11×). On sample 1, large dropped a whole sentence ("Fördelen är
att varje lager kan testas för sig"), a quality risk the WER figure hides.

If you measure yourself: whisper.cpp's `-nt` (no timestamps) merges the speech into a few lumps —
measured 3 segments at 18–46 s for 110 s of speech, against 24 segments at 1–5 s with timestamps —
and moves the WER figures by several percentage points. `notat` does not use the flag, and
`tools/jamfor.py` does the same so the numbers can be compared.

## Speakers: Deltagare 1, 2 …

Toggled in the bar menu (**Röster → Särskilj röster**) or with `notat röster på|av`. Your own
microphone is always **Du**; the voices in the meeting audio get **Deltagare 1, 2 …** sorted by
how much they talk (the one who talks most becomes 1). A paragraph that no measured turn covers
keeps "Mötet" — honestly empty rather than guessed.

The mechanism is **sherpa-onnx** (a static binary plus ONNX models, ~70 MB, no torch, no cloud
service): pyannote segmentation and voice embeddings (NeMo TitaNet small). The speaker is set on
every whisper segment *before* the paragraphs are merged — otherwise a paragraph can span several
voices and the label becomes a guess. `notat diar-hamta` fetches the models (install.sh does it
for you).

- If you know how many people are in the meeting, set `"antal_talare": 3` in the config — it is
  more accurate than the automation. Otherwise the count is found with the threshold 0.8
  (`NOTAT_DIAR_TRÖSKEL`); a sweep from 0.6 to 0.95 against a two-speaker sample with 16 known
  turns gave 100 % correct turns for 0.7–0.95 and 88 % for 0.6 — the plateau is wide, and too low
  a threshold splits the voices instead of merging them.
- **Measured:** on a sample of its own with two Swedish voices and 16 known turn changes, the
  automation gave **16/16 correct speakers in turn order**. On a real 58 s recording from a room
  it found four voices in a discussion that sounds like two or three: the auto mode is blunter on
  room noise.
- **Cost:** about 0.2 × the recording's length in CPU time (an hour ≈ 12 extra minutes) — which is
  why the switch is on/off and sits in the menu.

## Meeting title and participants

The meeting apps on Linux leave nothing reliable locally: Zoom's databases are encrypted
(`~/.zoom/data` has only `experiment` tables in clear text), Discord has no participant list in
any readable format, and the accessibility bus (AT-SPI) is disabled by default. `notat` therefore
does not guess — you write the names:

```bash
notat möte "Systemarkitektur 3"            # the title becomes the document heading
notat möte --deltagare "Ada, Bo"           # **Deltagare:** in the document
notat möte --namn "1=Ada, 2=Bo"            # Deltagare 1/2 in the transcript become the names
notat möte --rensa                         # clear title, participants and names
notat möte --mapp <recording-dir>          # point at an older recording
```

With no arguments the command shows which meeting it refers to. Without a running recording that
is the **latest** directory in `~/.local/share/notat/raw/`, and the answer says which one. The
values are written into the recording's `session.json` — the same file the transcription reads —
so the title and the participant list land in the document without extra steps. `--namn` applies
to the transcription that is coming: set it while you are recording, or run
`notat transcribe <dir>` again afterwards. A name only changes the label — the track number
behind it (`who#nr`) carries the duplicate and echo logic, and `Du`/`Mötet` are never renamed.

## Known voices: the name follows the voice

`Deltagare 1` applies to one recording. If you want the name to follow the voice between
meetings, name the speaker **once** — which you already do with `notat möte --namn "1=Ada"` — and
the voice is saved:

```bash
notat möte --namn "1=Ada" --mapp <recording-dir>   # names + saves the voice
notat transcribe <recording-dir>                   # the document is written with the name
notat namn                                         # show the registry
notat namn på|av                                   # toggle name matching
notat namn Ada ~/voice-samples/ada.wav             # save a voice from a file (16 kHz mono)
notat glöm Ada                                     # delete the voice profile
```

The next recording where Ada talks gets the name by itself — marked `Ada (röst)` in the document,
because it is a match and not a name you typed. If no known voice is found, `Deltagare N` stays:
no guessing. `notat devices` shows the registry and whether matching is `på`.

**The mechanism** is the sherpa binary that is already in `~/.local/share/notat/diar/` — no new
model, nothing new to install, nothing sent anywhere. The reference voice and an unknown turn are
put in the same file with one second of silence between them; run the diarisation and see whether
the turn lands in the same cluster as the reference. Cost: ~1.4 s per unknown voice in a
recording.

**Measured on `diarprov/`** (16 turns, two synthetic voices):

| Sample | Result |
|---|---|
| Same voice against different, isolated (`tur00`+`tur02` / `tur00`+`tur01`) | 1 cluster / 2 clusters — 4/4 correct |
| Unknown turn against two references, 14 turns, threshold sweep | **14/14 for 0.6–0.8**; 13/14 at sherpa's default 0.5; 10/14 at 0.9 |

The threshold is the dial, and the plateau is wide: below 0.5 the speaker splits into several
clusters, above 0.9 the **reference voices** merge (measured: 14/14 at 1.0) and then everyone
becomes the same person. `NOTAT_RÖST_TRÖSKEL` (default 0.7) sits in the middle of the plateau.
Measured with a separate embedding chain (`onnxruntime` + `numpy`, the same TitaNet model): the
same voice +0.87 in cosine against different +0.33 — but that needs a package that is not in the
repository, so the path above was chosen.

**The limit, honestly:** two synthetic voices in a clean recording. More voices, worse
microphones, bleed and a voice that changes over time are not measured — that is why the name is
marked `(röst)` in the document, why matching can be switched off, and why the voice profiles sit
in `~/.local/share/notat/röster/` with mode 0600 (directory 0700) and are deleted with
`notat glöm`.

## Where things end up

- **Documents:** `<vault>/Inspelningar/Möte YYYY-MM-DD HH-MM.md` (a title set with `notat möte`
  becomes the file name instead). The vault is `valv` in `~/.config/notat/config.json`, otherwise
  `vault_root` from `~/.config/omascribe/config.json`, otherwise `~/Documents/OmaScribe Vault`,
  otherwise `~/Documents/Anteckningar`.
  Shape: `## Sammanfattning` (bullets plus Beslut/Uppgifter/Nyckelbegrepp), `## Transkription`
  with speakers (`Mötet` = the audio output, `Du` = the microphone, `Deltagare 1, 2 …` when the
  voice switch is on) in time order, and `## Egna anteckningar`.
  The transcript is written first and the summary is added on top — if the AI service is down you
  never lose the transcript, only the summary (you get a notification).
- **Raw audio:** `~/.local/share/notat/raw/<timestamp>/*.wav` (16 kHz mono). Kept on purpose —
  `notat transcribe <dir>` can redo them.
- **Models:** `~/.local/share/notat/models/<id>/`.
- **Speaker separation:** `~/.local/share/notat/diar/` (the sherpa-onnx binary and the ONNX
  models, ~70 MB; `notat diar-hamta` fetches them).
- **Log:** `~/.local/share/notat/notat.log` (who called what).

## Settings — `~/.config/notat/config.json`

```json
{
  "uteslut": ["WCAM110BK"],
  "modell": "kb-whisper-small",
  "röster": true,
  "antal_talare": 0,
  "valv": "~/Documents/Anteckningar"
}
```

- `uteslut`: devices that must not be recorded (name or description *containing* the pattern,
  case-insensitive). `notat devices` lists them under `uteslutna`, so what was left out is
  visible instead of disappearing silently. The menu writes here.
- `modell`: the selected model (set by the menu).
- `röster`: separate the speakers in the document (the menu toggles it).
- `antal_talare`: 0 = find the count automatically; set the number if you know it.
- `valv`: where the documents go.

Environment variables: `NOTAT_MODEL` (path or id), `NOTAT_MODEL_DIR`, `NOTAT_LANG` (default
`auto`), `NOTAT_SINK`, `NOTAT_SOURCE`, `NOTAT_VAULT` (overrides `valv`, handy for test runs),
`NOTAT_DIAR_TRÖSKEL` (clustering threshold, default 0.8).

## VAD is not optional

Without the VAD model, whisper finds text in the silence. Measured: 5 minutes of digital silence
gave 10 invented segments without VAD ("you you You …") and 0 with Silero-VAD — and it is faster,
too. `install.sh` fetches `ggml-silero-v5.1.2.bin` (885 kB).

## Test

```bash
python3 test_notat.py              # pure logic: segments, paragraphs, audio duplicates, devices, model choice, speaker labels, title/participants, voices, search (28/28)
NOTAT_NATVERK=1 python3 test_notat.py   # + that every download URL returns a real file
bash tools/e2e.sh                  # end to end through a virtual sink (no audio in the room)
python3 tools/jamfor.py tools/facit.wav tools/facit.txt kb-whisper-small   # WER against known text
python3 tools/diarprov.py          # speaker separation against a synthetic two-speaker sample (16 turns)
python3 tools/spar.py              # per track: level and what whisper heard (troubleshooting)
```

`tools/facit.wav` is not included (it is an audio file) — build it yourself from the reference
text with any Swedish voice:

```bash
pip install edge-tts
edge-tts --voice sv-SE-SofieNeural --file tools/facit.txt --write-media /tmp/f.mp3
ffmpeg -i /tmp/f.mp3 -ac 1 -ar 16000 tools/facit.wav
```

## Troubleshooting

| Symptom | Cause / what to do |
|---|---|
| The document warns that the meeting audio was heard in the room | you are playing through loudspeakers — use headphones |
| The text appears twice | same as above; several microphones pick up the same voice |
| Invented text in the pauses | the VAD model is missing from `~/.local/share/notat/models/` |
| "hittar ingen whisper-modell" | pick/download one in the bar menu, or `notat hamta kb-whisper-small` |
| No text at all, the recording is silent | wrong device selected in the menu — `python3 tools/spar.py <dir>` shows dB per track |
| The bar button is not visible | `omarchy plugin enable io.github.alexwest1981.omanotation`, then `omarchy-restart-shell` |
| No document after the stop | `notat status --json` says whether the job is alive; the child's output is in `~/.local/share/notat/raw/<dir>/transcription.log`. Rerun with `notat transcribe "<dir>"` |

## Uninstall

```bash
omarchy plugin remove io.github.alexwest1981.omanotation   # the bar button
rm ~/.local/bin/notat                                      # the command
rm -rf ~/.config/notat ~/.local/share/notat                # config, models, voice profiles, raw audio
```

The documents stay in the vault (delete them there when you like) — `notat senaste` shows the
path. The `~/.local/share/notat` line also removes the raw recordings (`raw/`), the downloaded
models and the voice profiles; none of it lives outside those two directories.

## License

MIT (see LICENSE). The model weights carry their own licences: KB-Whisper is Apache-2.0 (KBLab,
the National Library of Sweden), OpenAI's Whisper weights are MIT. Silero-VAD is MIT. The speaker
separation uses sherpa-onnx (Apache-2.0), pyannote-segmentation-3.0 (MIT) and NVIDIA NeMo TitaNet
(the terms are on the NGC model page).
