#!/usr/bin/env python3
"""Mäter whisper-modeller mot en känd text: tid och ordagrannhet (WER).

  python3 tools/jamfor.py tools/facit.wav tools/facit.txt kb-whisper-large kb-whisper-small ...
  (utan modellargument: alla som finns nedladdade)

WER = andel fel ord efter att skiljetecken och skiftläge normaliserats. Talarbyte,
tystnad och pauser räknas inte - bara orden.
"""
import importlib.util
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROT = os.path.dirname(HERE)
spec = importlib.util.spec_from_loader(
    "notat", importlib.machinery.SourceFileLoader("notat", os.path.join(ROT, "notat")))
notat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notat)


def ordlista(text):
    text = text.lower()
    text = re.sub(r"[^\wåäöéüå\s]", " ", text)
    return [w for w in text.split() if w]


def wer(facit, hypotes, detaljer=False):
    """Ordnivå-Levenshtein: (fel, totalt) mot facit, och vilka fel som gjordes."""
    a, b = ordlista(facit), ordlista(hypotes)
    d = list(range(len(b) + 1))
    ops = []
    for i, x in enumerate(a, 1):
        ny = [i]
        rad = []
        for j, y in enumerate(b, 1):
            val = min((d[j] + 1, "del"), (ny[j - 1] + 1, "ins"),
                      (d[j - 1] + (x != y), "byt" if x != y else "="))
            ny.append(val[0])
            rad.append(val[1])
        d = ny
        ops.append(rad)
    if not detaljer:
        return d[-1], len(a)
    # baklänges genom matrisen: plocka ut de fel som faktiskt ligger i vägen
    i, j, fel = len(a), len(b), []
    while i > 0 or j > 0:
        steg = ops[i - 1][j - 1] if i > 0 and j > 0 else ("ins" if j > 0 else "del")
        if steg == "=":
            i, j = i - 1, j - 1
        elif steg == "byt":
            fel.append(f"byt: '{a[i-1]}' -> '{b[j-1]}'")
            i, j = i - 1, j - 1
        elif steg == "ins":
            fel.append(f"in: '{b[j-1]}'")
            j -= 1
        else:
            fel.append(f"ut: '{a[i-1]}'")
            i -= 1
    return d[-1], len(a), list(reversed(fel))


def kor(wav, modell, tag):
    ut = os.path.join("/tmp", f"wer-{tag}")
    vad = notat.find_vad()
    args = [notat.WHISPER, "-m", modell, "-f", wav, "-l", notat.LANG,
            "-oj", "-of", ut, "-t", "12", "-nt"]
    if vad:
        args += ["--vad", "-vm", vad]
    args += os.environ.get("NOTAT_WHISPER_EXTRA", "").split()
    t0 = time.time()
    r = subprocess.run(args, capture_output=True, text=True)
    tid = time.time() - t0
    if not os.path.exists(ut + ".json"):
        return None, tid, (r.stderr or r.stdout)[-200:]
    import json
    with open(ut + ".json", encoding="utf-8") as f:
        data = json.load(f)
    text = " ".join((s.get("text") or "").strip() for s in data.get("transcription", []))
    return text, tid, None


def längd(wav):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", wav], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    wav, facitfil = argv[0], argv[1]
    with open(facitfil, encoding="utf-8") as f:
        facit = f.read()
    dur = längd(wav)
    valda = argv[2:] or [m["id"] for m in notat.MODELLER if notat.modell_sökväg(m["id"])]
    print(f"ljud: {dur:.0f}s · språk: {notat.LANG} · VAD: {'ja' if notat.find_vad() else 'nej'}")
    print(f"{'modell':28} {'tid':>7} {'x realtid':>10} {'WER':>7}  fel/ord")
    rader = []
    for mid in valda:
        p = notat.modell_sökväg(mid) or mid
        if not os.path.exists(p):
            print(f"{mid:28} saknas")
            continue
        text, tid, fel = kor(wav, p, mid.replace('/', '_'))
        if text is None:
            print(f"{mid:28} FEL: {fel}")
            continue
        with open(f"/tmp/wer-{mid.replace('/', '_')}.txt", "w", encoding="utf-8") as f:
            f.write(text)
        f_, n, detaljer = wer(facit, text, detaljer=True)
        rader.append((mid, f_ / n))
        print(f"{mid:28} {tid:6.1f}s {dur / tid if tid else 0:9.1f}x {100 * f_ / n:6.1f}%  {f_}/{n}")
        for d in detaljer[:8]:
            print(f"      {d}")
        if len(detaljer) > 8:
            print(f"      ... {len(detaljer) - 8} till (utskriften: /tmp/wer-{mid.replace('/', '_')}.txt)")
    if len(rader) > 1:
        bäst = min(rader, key=lambda r: r[1])
        print(f"\nbäst på svenska: {bäst[0]} ({100 * bäst[1]:.1f}% WER)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
