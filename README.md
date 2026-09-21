# OmaNotation (kommandot: `notat`)

Mötes- och föreläsningsantecknare för Linux/Omarchy. Lyssnar på **båda ljudsidorna**
(mötet via ljudutgångarnas monitor, du via mikrofonerna), transkriberar med whisper.cpp
och skriver ett dokument när du stoppar. En knapp i Omarchys toppbar startar och stoppar.

*Meeting/lecture note taker for Linux: records every audio output and input, transcribes
with whisper.cpp (Swedish-tuned KB-Whisper recommended), writes a markdown document with
an AI summary. Bar widget in Omarchy; right-click picks sources, model and downloads.*

## Installation

```bash
git clone https://github.com/alexwest1981/OmaNotation.git
cd OmaNotation
./install.sh                       # kommando + VAD-modell + kb-whisper-small + bar-knapp
./install.sh --ingen-modell        # om du redan har en modell
```

Kräver `python3` (bara stdlib), `ffmpeg`, PipeWire (`pactl`) och `whisper-cli` i PATH —
bygg whisper.cpp med CUDA för din maskin:

```bash
git clone https://github.com/ggml-org/whisper.cpp && cd whisper.cpp
cmake -B build -DGGML_CUDA=ON && cmake --build build --config Release -j
cp build/bin/whisper-cli ~/.local/bin/
```

## Användning

| Kommando | Vad det gör |
|---|---|
| `notat` | startar om inget spelas in, stoppar + transkriberar annars |
| `notat start` / `notat stop` | samma sak, uttryckligen |
| `notat status [--json]` | läget (baren pollar den här) |
| `notat devices` | enheter, modell och valv som används |
| `notat valj <enhet>` | slå av/på en enhet (`notat valj alla` = allt på) |
| `notat modeller` | modellerna, vilken som är vald och vilka som finns nedladdade |
| `notat modell <id>` | byt modell |
| `notat hamta <id>` | ladda ner en modell (procent per rad) |
| `notat röster på\|av` | skilj talarna åt i dokumentet (Deltagare 1, 2 …) |
| `notat diar-hamta` | ladda ner talaruppdelningen (~70 MB) |
| `notat transcribe <mapp>` | gör om en tidigare inspelning (t.ex. med bättre modell) |
| `notat stop --no-summary` | hoppa över AI-sammanfattningen |

**Bar-knappen** (`custom.notat`, mikrofonikonen): vänsterklick startar/stoppar och visar
en räknare. **Högerklick** öppnar menyn i tre avsnitt: **Källor att spela in** (slå av/på
enheter), **Modell** (byt modell, nedladdning sköts automatiskt om den saknas) och
**Röster** (särskilj talarna). Klick utanför stänger menyn. Ändringar i menyn gäller nästa
inspelning — en pågående inspelning rörs inte.

## Var den lyssnar

**Alla** ljudutgångar (deras monitor: allt som spelas upp — Zoom, video, musik) och **alla**
ljudingångar (mikrofoner, line-in). En ffmpeg per enhet, en fil per enhet, så en enhet som
dör (urkopplad USB, upptagen HDMI) inte fäller de andra.

Samma ljud fångat av flera enheter slås ihop genom att **jämföra ljudet, inte texten**
(whisper skriver olika ord för samma mening beroende på vilken mikrofon som hörde den —
mätt 0,4 i textlikhet för samma sekund). Kuverten jämförs med korrelation och
fördröjningssökning, och den starkaste kopian behålls.

Styckesgränserna glider några sekunder mellan enheterna — whisper lägger samma mening på
t.ex. 46–48 s i ena spåret och 48–52 s i det andra (mätt). Paren matchas därför på **närhet i
tid**, och jämförelsen görs mot den andra enhetens ljud vid *samma* tidpunkt: 0,99 för samma
mening, mot 0,57 med den gamla jämförelsen där dubbletten gick igenom. Att i stället jämföra
ett gemensamt fönster duger inte — bär båda spåren samma ljud korrelerar vilket fönster som
helst (mätt 0,99 även för två stycken 20 sekunder isär), så hela mötet skulle slås ihop.

**Högtalare ger dubbletter som ingen heuristik kan ta bort.** Hör mikrofonen mötets ljud i
rummet är mikrofonens ljud inte en kopia av utgången utan en blandning (din röst + mötet),
och då står diskussionen två gånger. Dokumentet får en varning om det, med siffror:

> [!warning] Mötets ljud hördes i rummet (1 av 2 mikrofonstycken är samma ljud som utgången) …

Hörlurar (eller ekodämpning i mötesappen) ger en ren text. Mätt: mikrofon mot utgång ligger
på 0,64–0,70 i korrelation när ljudet hörs i rummet, medan olika ljud samtidigt ligger under 0,3.

Vill du hellre styra exakt: `NOTAT_SINK`/`NOTAT_SOURCE` låser inspelningen till två enheter.

## Modeller (mätt, inte gissat)

Whisper-modellerna väljs i bar-menyn eller med `notat modell <id>`. Katalogen innehåller
KBLab:s svensktränade **KB-Whisper** och OpenAI:s flerspråkiga. Uppmätt på två svenska prov med
känd text (272 och 342 ord, `tools/jamfor.py`) på en RTX 3060 Ti:

| Modell | Storlek | Prov 1 (119 s) | Prov 2 (143 s) | Fart |
|---|---|---|---|---|
| **kb-whisper-small** | 466 MB | **4,2 %** | 5,0 % | 26× realtid |
| kb-whisper-medium | 1,5 GB | 4,6 % | — | 18× |
| kb-whisper-large-q5 | 1,1 GB | 6,5 % | — | 8× |
| kb-whisper-large | 2,9 GB | 6,9 % | **3,8 %** | 11× |
| openai-small | 466 MB | 8,0 % | 6,7 % | 25× |

Läsningen: de svensktränade KB-Whisper-modellerna slår OpenAI small på båda proven, och
small/large ligger nära varandra och **byter plats beroende på material** — small är standardvalet
för farten (26× mot 11×). På prov 1 utelämnade large en hel mening ("Fördelen är att varje lager
kan testas för sig"), en kvalitetsrisk som WER-siffran döljer.

Mäter du själv: whisper.cpp:s `-nt` (utan tidsstämplar) slår ihop talet till några få klumpar —
mätt 3 segment på 18–46 s för 110 s tal, mot 24 segment på 1–5 s med tidsstämplar — och flyttar
WER-siffrorna flera procentenheter. `notat` använder inte flaggan, och `tools/jamfor.py` gör
detsamma så att siffrorna går att jämföra.

## Röster: Deltagare 1, 2 …

Växlas i bar-menyn (**Röster → Särskilj röster**) eller med `notat röster på|av`. Din egen
mikrofon blir alltid **Du**; rösterna i mötets ljud får **Deltagare 1, 2 …** sorterade efter hur
mycket de pratar (den som pratar mest blir 1). Ett stycke som inte täcks av någon uppmätt tur
behåller "Mötet" — hellre ärligt tomt än gissat.

Mekaniken är **sherpa-onnx** (statisk binär + ONNX-modeller, ~70 MB, ingen torch, ingen
molntjänst): pyannote-segmentering + röst-embedding (NeMo TitaNet small). Talaren sätts på varje
whisper-segment *innan* styckena slås ihop — annars kan ett stycke spänna flera röster och
etiketten blir en gissning. `notat diar-hamta` hämtar modellerna (install.sh gör det åt dig).

- Vet du hur många som deltar: sätt `"antal_talare": 3` i config — det är mer träffsäkert än
  automatiken. Annars hittas antalet med tröskeln 0,8 (`NOTAT_DIAR_TRÖSKEL`).
- **Mätt:** på ett eget prov med två svenska röster och 16 kända turbyten gav automatiken
  **16/16 rätt talare i turordning**. På en riktig 58 s-inspelning från ett rum hittade den fyra
  röster i en diskussion som låter som två–tre: auto-läget är trubbigare på rummel.
- **Kostnad:** cirka 0,2 × inspelningens längd i CPU-tid (en timme ≈ 12 minuter extra) — därför
  är växeln av/på och står i menyn.

## Var sakerna hamnar

- **Dokument:** `<valv>/Inspelningar/Möte ÅÅÅÅ-MM-DD TT-MM.md`. Valvet är `valv` i
  `~/.config/notat/config.json`, annars `vault_root` ur `~/.config/omascribe/config.json`,
  annars `~/Documents/OmaScribe Vault`, annars `~/Documents/Anteckningar`.
  Formen: `## Sammanfattning` (punkter + Beslut/Uppgifter/Nyckelbegrepp), `## Transkription`
  med talare (`Mötet` = ljudutgången, `Du` = mikrofonen, `Deltagare 1, 2 …` när röstväxeln är
  på) i tidsordning, och `## Egna anteckningar`.
  Utskriften skrivs först, sammanfattningen läggs ovanpå — är AI-tjänsten nere förlorar du
  aldrig utskriften, bara sammanfattningen (du får en notis).
- **Rå ljud:** `~/.local/share/notat/raw/<tidsstämpel>/*.wav` (16 kHz mono). Behålls med flit —
  `notat transcribe <mapp>` kan göra om dem.
- **Modeller:** `~/.local/share/notat/models/<id>/`.
- **Talarskiljning:** `~/.local/share/notat/diar/` (sherpa-onnx-binären och ONNX-modellerna,
  ~70 MB; `notat diar-hamta` hämtar dem).
- **Logg:** `~/.local/share/notat/notat.log` (vem anropade vad).

## Inställningar — `~/.config/notat/config.json`

```json
{
  "uteslut": ["WCAM110BK"],
  "modell": "kb-whisper-small",
  "röster": true,
  "antal_talare": 0,
  "valv": "~/Documents/Anteckningar"
}
```

- `uteslut`: enheter som inte ska spelas in (namn eller beskrivning som *innehåller* mönstret,
  skiftlägesoberoende). `notat devices` listar dem under `uteslutna`, så det syns vad som valts
  bort i stället för att försvinna tyst. Menyn skriver hit.
- `modell`: vald modell (sätts av menyn).
- `röster`: skilj talarna åt i dokumentet (menyn växlar).
- `antal_talare`: 0 = hitta antalet automatiskt; sätt antalet om du vet det.
- `valv`: var dokumenten hamnar.

Miljövariabler: `NOTAT_MODEL` (sökväg eller id), `NOTAT_MODEL_DIR`, `NOTAT_LANG` (default
`auto`), `NOTAT_SINK`, `NOTAT_SOURCE`, `NOTAT_VAULT` (överstyr `valv`, bra för provkörningar),
`NOTAT_DIAR_TRÖSKEL` (klustringströskel, default 0,8).

## VAD är inte valfritt

Utan VAD-modellen hittar whisper på text i tystnaden. Mätt: 5 minuter digital tystnad gav
10 påhittade segment utan VAD ("you you You …") och 0 med Silero-VAD — dessutom snabbare.
`install.sh` hämtar `ggml-silero-v5.1.2.bin` (885 kB).

## Test

```bash
python3 test_notat.py              # ren logik: segment, stycken, ljuddubbletter, enheter, modellval, talaretiketter (20/20)
NOTAT_NATVERK=1 python3 test_notat.py   # + att varje nedladdnings-URL ger en riktig fil
bash tools/e2e.sh                  # ände-till-ände via virtuell sink (inget ljud i rummet)
python3 tools/jamfor.py tools/facit.wav tools/facit.txt kb-whisper-small   # WER mot känd text
python3 tools/diarprov.py          # talaruppdelning mot ett syntetiskt tvåtalarsprov (16 turer)
python3 tools/spar.py              # per spår: nivå och vad whisper hörde (felsökning)
```

`tools/facit.wav` ingår inte (ljudfil) — gör den själv av facit-texten med valfri svensk röst:

```bash
pip install edge-tts
edge-tts --voice sv-SE-SofieNeural --file tools/facit.txt --write-media /tmp/f.mp3
ffmpeg -i /tmp/f.mp3 -ac 1 -ar 16000 tools/facit.wav
```

## Felsökning

| Symptom | Orsak / åtgärd |
|---|---|
| Dokumentet har varning om att mötets ljud hördes i rummet | du spelar i högtalare — använd hörlurar |
| Texten står två gånger | samma som ovan; flera mikrofoner tar upp samma röst |
| Påhittad text i pauserna | VAD-modellen saknas i `~/.local/share/notat/models/` |
| "hittar ingen whisper-modell" | välj/ladda ner en i bar-menyn, eller `notat hamta kb-whisper-small` |
| Ingen text alls, inspelningen är tyst | fel enhet vald i menyn — `python3 tools/spar.py <mapp>` visar dB per spår |
| Bar-knappen syns inte | `omarchy plugin enable custom.notat`, sedan `omarchy-restart-shell` |

## Licens

MIT (se LICENSE). Modellvikterna har egna licenser: KB-Whisper är Apache-2.0 (KBLab,
Kungliga biblioteket), OpenAI:s Whisper-vikter är MIT. Silero-VAD är MIT. Talarskiljningen
använder sherpa-onnx (Apache-2.0), pyannote-segmentation-3.0 (MIT) och NVIDIA NeMo TitaNet
(licensvillkoren står på NGC-modellsidan).
