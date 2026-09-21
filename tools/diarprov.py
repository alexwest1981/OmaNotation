#!/usr/bin/env python3
"""Bygger ett prov med KÄNDA talarbyten och poängsätter en diarisering mot det.

  python3 tools/diarprov.py bygg        # gör provet (två svenska röster, 16 turer)
  python3 tools/diarprov.py poang <rttm|sherpa-utskrift>

Facit är exakt: varje tur är en egen TTS-fil med känd längd, så gränserna är mätta,
inte gissade. Två röster räcker för att avgöra om diariseringen hittar rätt antal
talare och rätt turordning — fler röster kräver fler svenska TTS-röster än som finns.
"""
import json
import os
import re
import subprocess
import sys

HÄR = os.path.dirname(os.path.abspath(__file__))
PROV = os.path.join(HÄR, "..", "diarprov")
RÖSTER = ["sv-SE-SofieNeural", "sv-SE-MattiasNeural"]
PAUS = 0.7

# Talar A (Sofie) och B (Mattias) turas om - innehållet spelar ingen roll, bara rösterna
TURER = [
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


def längd(path):
    r = sh("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def bygg():
    os.makedirs(PROV, exist_ok=True)
    delar, facit, t = [], [], 0.0
    for i, text in enumerate(TURER):
        röst = RÖSTER[i % 2]
        mp3 = os.path.join(PROV, f"tur{i:02d}.mp3")
        wav = os.path.join(PROV, f"tur{i:02d}.wav")
        if not os.path.exists(wav):
            r = sh("edge-tts", "--voice", röst, "--text", text, "--write-media", mp3)
            if not os.path.exists(mp3) or os.path.getsize(mp3) < 1000:
                sys.exit(f"edge-tts misslyckades: {r.stderr[-200:]}")
            sh("ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
               "-i", mp3, "-ac", "1", "-ar", "16000", wav)
        d = längd(wav)
        facit.append({"talare": f"talare{i % 2}", "start": round(t, 2), "slut": round(t + d, 2)})
        delar.append(wav)
        t += d + PAUS
    tyst = os.path.join(PROV, "tyst.wav")
    if not os.path.exists(tyst):
        sh("ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
           "-t", str(PAUS), "-i", "anullsrc=r=16000:cl=mono", tyst)
    lista = os.path.join(PROV, "lista.txt")
    with open(lista, "w") as f:
        for d in delar:
            f.write(f"file '{d}'\nfile '{tyst}'\n")
    prov = os.path.join(PROV, "prov.wav")
    sh("ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
       "-f", "concat", "-safe", "0", "-i", lista, "-ac", "1", "-ar", "16000", prov)
    with open(os.path.join(PROV, "facit.json"), "w", encoding="utf-8") as f:
        json.dump(facit, f, ensure_ascii=False, indent=1)
    print(f"{prov}: {längd(prov):.1f}s, {len(TURER)} turer, 2 talare, facit i {PROV}/facit.json")
    return 0


def läs_turer(text):
    """sherpa-onnx-utskrift: '0.638 -- 6.848 speaker_00' (och RTTM-rader om sådana ges)."""
    ut = []
    for rad in text.splitlines():
        m = re.match(r"\s*([\d.]+)\s*--\s*([\d.]+)\s+(speaker_\d+)", rad)
        if m:
            ut.append({"start": float(m.group(1)), "slut": float(m.group(2)), "talare": m.group(3)})
            continue
        f = rad.split()
        if len(f) >= 8 and f[0] == "SPEAKER":      # RTTM
            ut.append({"start": float(f[3]), "slut": float(f[3]) + float(f[4]), "talare": f[7]})
    return ut


def poäng(fil):
    with open(os.path.join(PROV, "facit.json"), encoding="utf-8") as f:
        facit = json.load(f)
    with open(fil, encoding="utf-8", errors="replace") as f:
        ut = läs_turer(f.read())
    if not ut:
        sys.exit("hittade inga talarturer i utskriften")

    def överlapp(a, b):
        return max(0.0, min(a["slut"], b["slut"]) - max(a["start"], b["start"]))

    # varje referenstur får den talare som täcker mest av turen
    par, rätt, tomma = {}, 0, 0
    for tur in facit:
        bästa = max(ut, key=lambda u: överlapp(tur, u))
        if överlapp(tur, bästa) < 0.3 * (tur["slut"] - tur["start"]):
            tomma += 1
            continue
        par.setdefault(tur["talare"], bästa["talare"])
        if par[tur["talare"]] == bästa["talare"]:
            rätt += 1
    antal_hittade = len({u["talare"] for u in ut})
    print(f"referens: {len(facit)} turer, 2 talare")
    print(f"hittade:  {antal_hittade} talare, {len(ut)} turer")
    print(f"rätt talare: {rätt}/{len(facit) - tomma} turer"
          + (f" ({100 * rätt / max(1, len(facit) - tomma):.0f} %)" if facit else ""))
    if tomma:
        print(f"turer utan täckning: {tomma}")
    print(f"mappning: {par}")
    rätt_antal = antal_hittade == 2
    print(f"antal talare rätt: {'ja' if rätt_antal else 'NEJ'}")
    return 0 if (rätt_antal and rätt >= 0.8 * (len(facit) - tomma)) else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(bygg() if sys.argv[1] == "bygg" else poäng(sys.argv[2]))
