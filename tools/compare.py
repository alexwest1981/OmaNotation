#!/usr/bin/env python3
"""Measures whisper models against a known text: time and word accuracy (WER).

  python3 tools/compare.py tools/reference.wav tools/reference.txt kb-whisper-large kb-whisper-small ...
  (without model arguments: all that are downloaded)

WER = the share of wrong words after punctuation and case have been normalized. Speaker
changes, silence and pauses are not counted - only the words.
"""
import importlib.machinery   # the loader below needs it (echo.py had it, this file did not)
import importlib.util
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_loader(
    "notat", importlib.machinery.SourceFileLoader("notat", os.path.join(ROOT, "notat")))
notat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notat)


def words(text):
    text = text.lower()
    text = re.sub(r"[^\wåäöéüå\s]", " ", text)   # keeps Swedish letters so WER stays honest
    return [w for w in text.split() if w]


def wer(reference, hypothesis, details=False):
    """Word-level Levenshtein: (errors, total) against the reference, and which errors were made."""
    a, b = words(reference), words(hypothesis)
    d = list(range(len(b) + 1))
    ops = []
    for i, x in enumerate(a, 1):
        new = [i]
        row = []
        for j, y in enumerate(b, 1):
            choice = min((d[j] + 1, "del"), (new[j - 1] + 1, "ins"),
                         (d[j - 1] + (x != y), "sub" if x != y else "="))
            new.append(choice[0])
            row.append(choice[1])
        d = new
        ops.append(row)
    if not details:
        return d[-1], len(a)
    # backwards through the matrix: pick out the errors that are actually in the way
    i, j, errors = len(a), len(b), []
    while i > 0 or j > 0:
        step = ops[i - 1][j - 1] if i > 0 and j > 0 else ("ins" if j > 0 else "del")
        if step == "=":
            i, j = i - 1, j - 1
        elif step == "sub":
            errors.append(f"sub: '{a[i-1]}' -> '{b[j-1]}'")
            i, j = i - 1, j - 1
        elif step == "ins":
            errors.append(f"ins: '{b[j-1]}'")
            j -= 1
        else:
            errors.append(f"del: '{a[i-1]}'")
            i -= 1
    return d[-1], len(a), list(reversed(errors))


def run(wav, model, tag):
    out = os.path.join("/tmp", f"wer-{tag}")
    vad = notat.find_vad()
    args = [notat.WHISPER, "-m", model, "-f", wav, "-l", notat.LANG,
            "-oj", "-of", out, "-t", "12"]
    if vad:
        args += ["--vad", "-vm", vad]
    args += os.environ.get("NOTAT_WHISPER_EXTRA", "").split()
    t0 = time.time()
    r = subprocess.run(args, capture_output=True, text=True)
    elapsed = time.time() - t0
    if not os.path.exists(out + ".json"):
        return None, elapsed, (r.stderr or r.stdout)[-200:]
    import json
    with open(out + ".json", encoding="utf-8") as f:
        data = json.load(f)
    text = " ".join((s.get("text") or "").strip() for s in data.get("transcription", []))
    return text, elapsed, None


def duration(wav):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", wav], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    wav, reference_file = argv[0], argv[1]
    with open(reference_file, encoding="utf-8") as f:
        reference = f.read()
    dur = duration(wav)
    chosen = argv[2:] or [m["id"] for m in notat.MODELS if not notat.model_path(m["id"])]
    print(f"audio: {dur:.0f}s · language: {notat.LANG} · VAD: {'yes' if notat.find_vad() else 'no'}")
    print(f"{'model':28} {'time':>7} {'x realtime':>10} {'WER':>7}  errors/words")
    rows = []
    for mid in chosen:
        p = notat.model_path(mid) or mid
        if not os.path.exists(p):
            print(f"{mid:28} missing")
            continue
        text, elapsed, err = run(wav, p, mid.replace('/', '_'))
        if text is None:
            print(f"{mid:28} ERROR: {err}")
            continue
        with open(f"/tmp/wer-{mid.replace('/', '_')}.txt", "w", encoding="utf-8") as f:
            f.write(text)
        n_err, n, details = wer(reference, text, details=True)
        rows.append((mid, n_err / n))
        print(f"{mid:28} {elapsed:6.1f}s {dur / elapsed if elapsed else 0:9.1f}x {100 * n_err / n:6.1f}%  {n_err}/{n}")
        for d in details[:8]:
            print(f"      {d}")
        if len(details) > 8:
            print(f"      ... {len(details) - 8} more (the output: /tmp/wer-{mid.replace('/', '_')}.txt)")
    if len(rows) > 1:
        best = min(rows, key=lambda r: r[1])
        print(f"\nbest: {best[0]} ({100 * best[1]:.1f}% WER)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
