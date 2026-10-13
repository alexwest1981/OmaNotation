#!/usr/bin/env python3
"""Per track: device, level and what whisper found. Diagnosis, not guessing.

  python3 tools/probe.py [dir]     (without dir: the latest recording)
"""
import json
import os
import re
import subprocess
import sys

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


def mean_db(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else None


for t in meta["tracks"]:
    wav = os.path.join(RAW, t["file"])
    js = os.path.join(RAW, os.path.splitext(t["file"])[0] + ".json")
    text = ""
    segs = 0
    if os.path.exists(js):
        d = json.load(open(js, encoding="utf-8"))
        segs = len(d.get("transcription", []))
        text = " ".join(s["text"].strip() for s in d.get("transcription", []))
    print(f"{t['file']:8} {t['label']:6} {mean_db(wav):7.1f} dB  {segs} seg  {t['desc'][:38]}")
    if text:
        print(f"         {text[:200]}")
