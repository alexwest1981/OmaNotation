#!/usr/bin/env python3
"""Builds a sample with KNOWN speaker changes and scores a diarisation against it.

  python3 tools/diar-sample.py build        # make the sample (two Swedish voices, 16 turns)
  python3 tools/diar-sample.py score <rttm|sherpa output>

The reference is exact: every turn is its own TTS file with a known length, so the boundaries
are measured, not guessed. Two voices are enough to tell whether the diarisation finds the right
number of speakers and the right turn order - more voices require more Swedish TTS voices than exist.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "..", "diar-sample")
VOICES = ["sv-SE-SofieNeural", "sv-SE-MattiasNeural"]
PAUSE = 0.7

# Speaker A (Sofie) and B (Mattias) take turns - the content does not matter, only the voices
TURNS = [
    "Hej, ska vi gå igenom hur vi lägger upp det här arbetet?",
    "Ja, absolut. Jag tänkte att vi börjar med att titta på kraven.",
    "Bra. Jag har läst igenom uppgiften och det står att vi ska lämna in på fredag.",
    "Okej, då har vi två veckor på oss. Hur mycket hinner vi?",
    "Jag tror vi kan bli klara om vi delar upp det. Jag tar databasen.",
    "Då tar jag gränssnittet och testerna. Men vi måste prata om arkitekturen först.",
    "Jag tycker vi kör en lagerarkitektur, det är enklast att förklara.",
    "Hmm, men blir det inte svårt att testa då? Vi kanske ska köra händelser i stället.",
    "Nej, jag tror faktiskt att lagren räcker för den här storleken på systemet.",
    "Okej, då gör vi så. Men vi skriver ner varför vi valde det.",
    "Självklart. Ska vi bestämma att vi träffas varje tisdag klockan tio?",
    "Det passar bra. Jag skriver in det i kalendern direkt.",
    "Gör det. Och så skickar jag ett utkast till kravspecifikationen i morgon.",
    "Toppen. Då säger vi det, vi hörs på tisdag.",
    "Just det, en sak till. Har du fått någon återkoppling från förra inlämningen?",
    "Ja, den var godkänd. Men de ville att vi skulle skriva tydligare motiveringar.",
]


def sh(*args):
    return subprocess.run(args, capture_output=True, text=True)


def duration(path):
    r = sh("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def build():
    os.makedirs(SAMPLE, exist_ok=True)
    parts, reference, t = [], [], 0.0
    for i, text in enumerate(TURNS):
        voice = VOICES[i % 2]
        mp3 = os.path.join(SAMPLE, f"turn{i:02d}.mp3")
        wav = os.path.join(SAMPLE, f"turn{i:02d}.wav")
        if not os.path.exists(wav):
            r = sh("edge-tts", "--voice", voice, "--text", text, "--write-media", mp3)
            if not os.path.exists(mp3) or os.path.getsize(mp3) < 1000:
                sys.exit(f"edge-tts failed: {r.stderr[-200:]}")
            sh("ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
               "-i", mp3, "-ac", "1", "-ar", "16000", wav)
        d = duration(wav)
        reference.append({"speaker": f"speaker{i % 2}", "start": round(t, 2), "end": round(t + d, 2)})
        parts.append(wav)
        t += d + PAUSE
    silence = os.path.join(SAMPLE, "silence.wav")
    if not os.path.exists(silence):
        sh("ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
           "-t", str(PAUSE), "-i", "anullsrc=r=16000:cl=mono", silence)
    listfile = os.path.join(SAMPLE, "list.txt")
    with open(listfile, "w") as f:
        for d in parts:
            f.write(f"file '{d}'\nfile '{silence}'\n")
    sample = os.path.join(SAMPLE, "sample.wav")
    sh("ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
       "-f", "concat", "-safe", "0", "-i", listfile, "-ac", "1", "-ar", "16000", sample)
    with open(os.path.join(SAMPLE, "reference.json"), "w", encoding="utf-8") as f:
        json.dump(reference, f, ensure_ascii=False, indent=1)
    print(f"{sample}: {duration(sample):.1f}s, {len(TURNS)} turns, 2 speakers, reference in {SAMPLE}/reference.json")
    return 0


def read_turns(text):
    """sherpa-onnx output: '0.638 -- 6.848 speaker_00' (and RTTM lines if given)."""
    out = []
    for line in text.splitlines():
        m = re.match(r"\s*([\d.]+)\s*--\s*([\d.]+)\s+(speaker_\d+)", line)
        if m:
            out.append({"start": float(m.group(1)), "end": float(m.group(2)), "speaker": m.group(3)})
            continue
        f = line.split()
        if len(f) >= 8 and f[0] == "SPEAKER":      # RTTM
            out.append({"start": float(f[3]), "end": float(f[3]) + float(f[4]), "speaker": f[7]})
    return out


def score(path):
    with open(os.path.join(SAMPLE, "reference.json"), encoding="utf-8") as f:
        reference = json.load(f)
    with open(path, encoding="utf-8", errors="replace") as f:
        out = read_turns(f.read())
    if not out:
        sys.exit("found no speaker turns in the output")

    def overlap(a, b):
        return max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))

    # every reference turn gets the speaker that covers the most of the turn
    mapping, correct, empty = {}, 0, 0
    for turn in reference:
        best = max(out, key=lambda u: overlap(turn, u))
        if overlap(turn, best) < 0.3 * (turn["end"] - turn["start"]):
            empty += 1
            continue
        mapping.setdefault(turn["speaker"], best["speaker"])
        if mapping[turn["speaker"]] == best["speaker"]:
            correct += 1
    found_count = len({u["speaker"] for u in out})
    print(f"reference: {len(reference)} turns, 2 speakers")
    print(f"found:     {found_count} speakers, {len(out)} turns")
    print(f"correct speaker: {correct}/{len(reference) - empty} turns"
          + (f" ({100 * correct / max(1, len(reference) - empty):.0f} %)" if reference else ""))
    if empty:
        print(f"turns without coverage: {empty}")
    print(f"mapping: {mapping}")
    count_ok = found_count == 2
    print(f"speaker count correct: {'yes' if count_ok else 'NO'}")
    return 0 if (count_ok and correct >= 0.8 * (len(reference) - empty)) else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(build() if sys.argv[1] == "build" else score(sys.argv[2]))
