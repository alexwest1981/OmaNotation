# notat

Mötes- och föreläsningsantecknare för Linux/Omarchy. Lyssnar på **båda ljudsidorna**
(mötet via ljudutgångens monitor, du via mikrofonen), transkriberar med whisper.cpp
och skriver ett dokument i OmaScribe-valvet när du stoppar.

## Användning

| Kommando | Vad det gör |
|---|---|
| `notat` | startar om inget spelas in, stoppar + transkriberar annars |
| `notat start` / `notat stop` | samma sak, uttryckligen |
| `notat status [--json]` | läget (baren pollar den här) |
| `notat transcribe <mapp>` | gör om en tidigare inspelning (t.ex. med bättre modell) |
| `notat stop --no-summary` | hoppa över AI-sammanfattningen |
| `notat devices` | vilka enheter/modeller/valv som används |

Knappen i Omarchys toppbar (`custom.notat`) gör samma sak som `notat`:
klick = start/stopp, högerklick = öppna mappen med dokumenten.

## Var sakerna hamnar

- **Dokument:** `<valv>/Inspelningar/Möte ÅÅÅÅ-MM-DD TT-MM.md` (`vault_root` läses ur
  `~/.config/omascribe/config.json`, annars `~/Documents/OmaScribe Vault`).
  Formen: `## Sammanfattning` (översikt i punkter + Beslut/Uppgifter/Nyckelbegrepp),
  `## Transkription` med talare (`Mötet` = ljudutgången, `Du` = mikrofonen) flätade i
  tidsordning, och en tom `## Egna anteckningar`.
  Skrivs i två steg: utskriften först, sammanfattningen ovanpå. Är AI-tjänsten nere eller
  långsam förlorar du aldrig utskriften — du får en notis i stället.
  Utskrifter över 16 000 tecken sammanfattas i delar som slås ihop (en timme ≈ 50 000 tecken).
- **Rå ljud:** `~/.local/share/notat/raw/<tidsstämpel>/{remote,mic}.wav` (16 kHz mono).
  Behålls med flit — `notat transcribe <mapp>` kan göra om dem.
- **Logg:** `~/.local/share/notat/notat.log` (vem anropade vad, med föräldraprocess).

## Var den lyssnar

**Alla** ljudutgångar (via deras monitor — allt som spelas upp: Zoom, video, musik) och
**alla** ljudingångar (mikrofoner, line-in). En ffmpeg per enhet och en fil per enhet, så en
enhet som dör (urkopplad USB, upptagen HDMI) inte fäller de andra. På den här maskinen blir
det sju spår: 3 utgångar + 3 ingångar (Q2U-mic, webbkameramic, line-in).

Samma mening som fångas av flera enheter — två mikrofoner hör samma röst, och hör de
dessutom högtalarna kommer den en gång till — slås ihop automatiskt. Utgångarnas kopior
vinner över mikrofonernas (linjeljud slår akustiskt), och vilka enheter som gav ljud står i
rubriken. `NOTAT_SINK`/`NOTAT_SOURCE` låser inspelningen till exakt två enheter (test, eller
när du vill välja ljudkort själv).

## Beroenden

- `whisper-cli` (`~/.local/bin`) + `ggml-small.bin` (letas i `NOTAT_MODEL_DIR`,
  `~/.local/share/notat/models`, `~/Work/novacut/models`).
- **VAD-modell** `ggml-silero-v5.1.2.bin` i `~/.local/share/notat/models/` — inte valfritt, se nedan.
- `ffmpeg`, `pactl`, `pw-play` (test), PipeWire.

Miljövariabler: `NOTAT_MODEL_DIR`, `NOTAT_LANG` (default `auto`), `NOTAT_SINK`, `NOTAT_SOURCE`.

## Mätt på den här maskinen

| Vad | Resultat |
|---|---|
| whisper small, CUDA (3060 Ti) | 16 s ljud på 0,8 s (~19× realtid) |
| Utan VAD, 5 min digital tystnad | 10 segment påhittad text ("you you You …") |
| Med VAD, samma tystnad | 0 segment — och snabbare |

Slutsatsen: VAD är inte en finess utan det som hindrar en timmes föreläsning från att
fyllas av påhittad text under pauserna.

## Test

```bash
python3 test_notat.py          # ren logik: segment, stycken, dubbletter, enheter (13/13)
bash tools/e2e.sh              # ände-till-ände via virtuell sink (inget ljud i rummet)
```

`tools/e2e.sh` skapar en egen null-sink, spelar in båda benen från den (så att
**inget ljud går ut i rummet och rummet inte spelas in**) och kontrollerar att ett
dokument skapas.
