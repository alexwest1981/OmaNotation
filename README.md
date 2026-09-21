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
| `notat transcribe <mapp>` | gör om en tidigare inspelning (t.ex. med bättre modell) |
| `notat stop --no-summary` | hoppa över AI-sammanfattningen |

**Bar-knappen** (`custom.notat`, mikrofonikonen): vänsterklick startar/stoppar och visar
en räknare. **Högerklick** öppnar menyn: vilka enheter som spelas in, vilken modell som
körs, och en nedladdningsknapp för de modeller som inte finns på disken än. Klick utanför
stänger menyn. Ändringar i menyn gäller nästa inspelning — en pågående inspelning rörs inte.

## Var den lyssnar

**Alla** ljudutgångar (deras monitor: allt som spelas upp — Zoom, video, musik) och **alla**
ljudingångar (mikrofoner, line-in). En ffmpeg per enhet, en fil per enhet, så en enhet som
dör (urkopplad USB, upptagen HDMI) inte fäller de andra.

Samma ljud fångat av flera enheter slås ihop genom att **jämföra ljudet, inte texten**
(whisper skriver olika ord för samma mening beroende på vilken mikrofon som hörde den —
mätt 0,4 i textlikhet för samma sekund). Kuverten jämförs med korrelation och
fördröjningssökning, och den starkaste kopian behålls.

**Högtalare ger dubbletter som ingen heuristik kan ta bort.** Hör mikrofonen mötets ljud i
rummet är mikrofonens ljud inte en kopia av utgången utan en blandning (din röst + mötet),
och då står diskussionen två gånger. Dokumentet får en varning om det, med siffror:

> [!warning] Mötets ljud hördes i rummet (1 av 2 mikrofonstycken är samma ljud som utgången) …

Hörlurar (eller ekodämpning i mötesappen) ger en ren text. Mätt: mikrofon mot utgång ligger
på 0,64–0,70 i korrelation när ljudet hörs i rummet, medan olika ljud samtidigt ligger under 0,3.

Vill du hellre styra exakt: `NOTAT_SINK`/`NOTAT_SOURCE` låser inspelningen till två enheter.

## Modeller (mätt, inte gissat)

Whisper-modellerna väljs i bar-menyn eller med `notat modell <id>`. Katalogen innehåller
KBLab:s svensktränade **KB-Whisper** och OpenAI:s flerspråkiga. Uppmätt på 119 s svenskt tal
med känd text (272 ord, `tools/jamfor.py tools/facit.wav tools/facit.txt`) på en RTX 3060 Ti:

| Modell | Storlek | WER | Fart | Kommentar |
|---|---|---|---|---|
| **kb-whisper-small** | 466 MB | **3,1 %** | 29× realtid | rekommenderas — bäst och snabbast i provet |
| kb-whisper-medium | 1,5 GB | 4,6 % | 8× | tappade första meningen i provet (både med och utan VAD) |
| kb-whisper-large-q5 | 1,1 GB | 6,9 % | 10× | |
| kb-whisper-large | 2,9 GB | 7,3 % | 4–13× | fler ordfel än small i provet; tappar enstaka ord |
| openai-small | 466 MB | 8,4 % | 31× | flerspråkig, sämre på svenska |
| openai-large-v3-turbo | 1,6 GB | — | — | flerspråkig, bra för engelska möten |

Samma slutsats på en riktig inspelning från ett rum (58 s, ingen facit): kb-whisper-small gav
den renaste texten utan påhittade ord, medan medium tappade de första ~25 orden och large
skrev "Tekniskt sett" där small hörde rätt. **Byter du modell: mät själv** med
`tools/jamfor.py` mot ett eget facit — siffrorna ovan gäller den här maskinen och den här typen av tal.

## Var sakerna hamnar

- **Dokument:** `<valv>/Inspelningar/Möte ÅÅÅÅ-MM-DD TT-MM.md`. Valvet är `valv` i
  `~/.config/notat/config.json`, annars `vault_root` ur `~/.config/omascribe/config.json`,
  annars `~/Documents/OmaScribe Vault`, annars `~/Documents/Anteckningar`.
  Formen: `## Sammanfattning` (punkter + Beslut/Uppgifter/Nyckelbegrepp), `## Transkription`
  med talare (`Mötet` = ljudutgången, `Du` = mikrofonen) i tidsordning, och `## Egna anteckningar`.
  Utskriften skrivs först, sammanfattningen läggs ovanpå — är AI-tjänsten nere förlorar du
  aldrig utskriften, bara sammanfattningen (du får en notis).
- **Rå ljud:** `~/.local/share/notat/raw/<tidsstämpel>/*.wav` (16 kHz mono). Behålls med flit —
  `notat transcribe <mapp>` kan göra om dem.
- **Modeller:** `~/.local/share/notat/models/<id>/`.
- **Logg:** `~/.local/share/notat/notat.log` (vem anropade vad).

## Inställningar — `~/.config/notat/config.json`

```json
{
  "uteslut": ["WCAM110BK"],
  "modell": "kb-whisper-small",
  "valv": "~/Documents/Anteckningar"
}
```

- `uteslut`: enheter som inte ska spelas in (namn eller beskrivning som *innehåller* mönstret,
  skiftlägesoberoende). `notat devices` listar dem under `uteslutna`, så det syns vad som valts
  bort i stället för att försvinna tyst. Menyn skriver hit.
- `modell`: vald modell (sätts av menyn).
- `valv`: var dokumenten hamnar.

Miljövariabler: `NOTAT_MODEL` (sökväg eller id), `NOTAT_MODEL_DIR`, `NOTAT_LANG` (default
`auto`), `NOTAT_SINK`, `NOTAT_SOURCE`.

## VAD är inte valfritt

Utan VAD-modellen hittar whisper på text i tystnaden. Mätt: 5 minuter digital tystnad gav
10 påhittade segment utan VAD ("you you You …") och 0 med Silero-VAD — dessutom snabbare.
`install.sh` hämtar `ggml-silero-v5.1.2.bin` (885 kB).

## Test

```bash
python3 test_notat.py              # ren logik: segment, stycken, ljuddubbletter, enheter, modellval (18/18)
NOTAT_NATVERK=1 python3 test_notat.py   # + att varje nedladdnings-URL ger en riktig fil
bash tools/e2e.sh                  # ände-till-ände via virtuell sink (inget ljud i rummet)
python3 tools/jamfor.py tools/facit.wav tools/facit.txt kb-whisper-small   # WER mot känd text
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
Kungliga biblioteket), OpenAI:s Whisper-vikter är MIT. Silero-VAD är MIT.
