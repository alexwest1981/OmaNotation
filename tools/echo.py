#!/usr/bin/env python3
"""How much of each microphone paragraph is echo of an output? Measure, do not guess."""
import importlib.util
import importlib.machinery
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_loader("notat", importlib.machinery.SourceFileLoader("notat", os.path.join(HERE, "..", "notat")))
notat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notat)

RAW_ROOT = os.path.join(os.path.expanduser("~"), ".local/share/notat/raw")


def latest():
    if not os.path.isdir(RAW_ROOT):
        return ""
    folders = [os.path.join(RAW_ROOT, d) for d in os.listdir(RAW_ROOT)]
    return max(folders, key=os.path.getmtime) if folders else ""


RAW = sys.argv[1] if len(sys.argv) > 1 else latest()
if not RAW or not os.path.isdir(RAW):
    sys.exit(f"usage: {sys.argv[0]} <dir with session.json>   (no recordings in {RAW_ROOT})")
meta = json.load(open(os.path.join(RAW, "session.json"), encoding="utf-8"))

envs, text = {}, {}
for i, t in enumerate(meta["tracks"], 1):
    wav = os.path.join(RAW, t["file"])
    envs[i] = notat.envelope(wav) if os.path.exists(wav) else (None, 0.0)
    js = os.path.join(RAW, os.path.splitext(t["file"])[0] + ".json")
    data = json.load(open(js, encoding="utf-8")) if os.path.exists(js) else {"transcription": []}
    text[i] = notat.paragraphs(notat.segments(data, f"{t['label']}#{i}"))

print("tracks:", {i: f"{meta['tracks'][i-1]['label']} {meta['tracks'][i-1]['file']}" for i in envs})


def piece(env, hop, a, b):
    return env[int(a / hop):int(b / hop)]


def echo_share(a, b, window=1.0, ratio=0.85, hop=0.02):
    n = max(1, int(window / hop))
    hits = total = 0
    for i in range(0, min(len(a), len(b)), n):
        x, y = a[i:i + n], b[i:i + n]
        if len(x) < 5:
            break
        total += 1
        if notat.korr(x, y) >= ratio:
            hits += 1
    return (hits / total) if total else 0.0


for i, paras_i in text.items():
    for j, paras_j in text.items():
        if i >= j:
            continue
        for p in paras_i:
            for q in paras_j:
                shortest = min(p[1] - p[0], q[1] - q[0])
                if shortest <= 0 or min(p[1], q[1]) - max(p[0], q[0]) < 0.5 * shortest:
                    continue
                e1, h1 = envs[i]
                e2, h2 = envs[j]
                if not e1 or not e2:
                    continue
                a = piece(e1, h1, p[0], p[1])
                b = piece(e2, h2, q[0], q[1])
                print(f"\ntrack {i} ({meta['tracks'][i-1]['label']}) [{p[0]:.1f}-{p[1]:.1f}] vs track {j} "
                      f"({meta['tracks'][j-1]['label']}) [{q[0]:.1f}-{q[1]:.1f}]")
                print(f"   whole paragraph correlation: {notat.korr(a, b):.2f}")
                print(f"   share of 1 s windows with corr>=0.85: {echo_share(a, b):.2f} (a vs b), {echo_share(b, a):.2f} (b vs a)")
                print(f"   level: {sum(a)/max(1,len(a)):.0f} vs {sum(b)/max(1,len(b)):.0f}")
                print(f"   text a: {p[3][:80]}")
                print(f"   text b: {q[3][:80]}")
