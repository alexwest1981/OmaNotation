#!/usr/bin/env python3
"""Hur mycket av varje mikrofonstycke är eko av en utgång? Mät, gissa inte."""
import importlib.util
import importlib.machinery
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_loader("notat", importlib.machinery.SourceFileLoader("notat", os.path.join(HERE, "..", "notat")))
notat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notat)

RAW = sys.argv[1] if len(sys.argv) > 1 else "/home/alex/.local/share/notat/raw/2026-09-21 10-39"
meta = json.load(open(os.path.join(RAW, "session.json"), encoding="utf-8"))

envs, text = {}, {}
for i, t in enumerate(meta["tracks"], 1):
    wav = os.path.join(RAW, t["file"])
    envs[i] = notat.envelope(wav) if os.path.exists(wav) else (None, 0.0)
    js = os.path.join(RAW, os.path.splitext(t["file"])[0] + ".json")
    data = json.load(open(js, encoding="utf-8")) if os.path.exists(js) else {"transcription": []}
    text[i] = notat.paragraphs(notat.segments(data, f"{t['label']}#{i}"))

print("spår:", {i: f"{meta['tracks'][i-1]['label']} {meta['tracks'][i-1]['file']}" for i in envs})


def stycke(env, hop, a, b):
    return env[int(a / hop):int(b / hop)]


def eko_andel(a, b, fönster=1.0, ratio=0.85, hop=0.02):
    n = max(1, int(fönster / hop))
    träff = tot = 0
    for i in range(0, min(len(a), len(b)), n):
        x, y = a[i:i + n], b[i:i + n]
        if len(x) < 5:
            break
        tot += 1
        if notat.korr(x, y) >= ratio:
            träff += 1
    return (träff / tot) if tot else 0.0


for i, paras_i in text.items():
    for j, paras_j in text.items():
        if i >= j:
            continue
        for p in paras_i:
            for q in paras_j:
                kortast = min(p[1] - p[0], q[1] - q[0])
                if kortast <= 0 or min(p[1], q[1]) - max(p[0], q[0]) < 0.5 * kortast:
                    continue
                e1, h1 = envs[i]
                e2, h2 = envs[j]
                if not e1 or not e2:
                    continue
                a = stycke(e1, h1, p[0], p[1])
                b = stycke(e2, h2, q[0], q[1])
                print(f"\nspår {i} ({meta['tracks'][i-1]['label']}) [{p[0]:.1f}-{p[1]:.1f}] mot spår {j} "
                      f"({meta['tracks'][j-1]['label']}) [{q[0]:.1f}-{q[1]:.1f}]")
                print(f"   hel stycke-korrelation: {notat.korr(a, b):.2f}")
                print(f"   andel 1 s-fönster med korr>=0.85: {eko_andel(a, b):.2f} (a mot b), {eko_andel(b, a):.2f} (b mot a)")
                print(f"   nivå: {sum(a)/max(1,len(a)):.0f} mot {sum(b)/max(1,len(b)):.0f}")
                print(f"   text a: {p[3][:80]}")
                print(f"   text b: {q[3][:80]}")
