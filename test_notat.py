#!/usr/bin/env python3
"""Kontroller av notat:s logik som inte kräver ljudenheter.

  python3 test_notat.py     (0 = allt ok)
"""
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_loader("notat", importlib.machinery.SourceFileLoader("notat", os.path.join(HERE, "notat")))
notat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notat)


def test_segments_hoppar_over_brus():
    data = {"transcription": [
        {"offsets": {"from": 0, "to": 2000}, "text": " Hej och välkomna till föreläsningen. "},
        {"offsets": {"from": 2000, "to": 3000}, "text": ""},
        {"offsets": {"from": 3000, "to": 4000}, "text": "[Musik]"},
        {"offsets": {"from": 4000, "to": 5000}, "text": " (musik spelas) "},
        {"offsets": {"from": 5000, "to": 6000}, "text": "Tentan är den tolfte."},
    ]}
    segs = notat.segments(data, "Mötet")
    assert [s[3] for s in segs] == ["Hej och välkomna till föreläsningen.", "Tentan är den tolfte."], segs
    assert segs[0][0] == 0.0 and segs[1][0] == 5.0, segs        # offset i ms -> sekunder


def test_paragraphs_slar_ihop_samma_talare():
    segs = [(0, 2, "Mötet", "Hej"), (2.5, 4, "Mötet", "allihop"), (10, 12, "Du", "Hej själv"),
            (12.1, 13, "Du", "tack"), (14, 15, "Mötet", "Bra")]
    paras = notat.paragraphs(segs)
    assert [p[2] for p in paras] == ["Mötet", "Du", "Mötet"], paras
    assert paras[0][3] == "Hej allihop", paras          # < 3 s mellanrum -> samma stycke
    assert paras[1][3] == "Hej själv tack", paras
    assert paras[2][3] == "Bra", paras


def test_paragraphs_bryter_langa_stycken():
    segs = [(i, i + 1, "Mötet", "x" * 250) for i in range(4)]
    assert len(notat.paragraphs(segs, maxlen=400)) > 1


def test_stycken_sorteras_efter_bada_sparen():
    remote = [(5.0, 7.0, "Mötet", "fråga")]
    mic = [(0.5, 3.0, "Du", "svar")]
    assert [s[2] for s in sorted(remote + mic, key=lambda s: s[0])] == ["Du", "Mötet"]


def test_mmss():
    assert notat.mmss(0) == "00:00" and notat.mmss(3661) == "61:01"


def test_enheter_kraver_monitor_suffix():
    # .monitor ska inte dubbleras, och ett uttryckligt NOTAT_SINK ska vinna
    old = os.environ.copy()
    os.environ["NOTAT_SINK"] = "notat_test.monitor"
    os.environ["NOTAT_SOURCE"] = "mic"
    try:
        tracks = notat.device_list()
        assert tracks[0][1] == "notat_test.monitor", tracks
        assert tracks[1][1] == "mic", tracks
    finally:
        os.environ.clear()
        os.environ.update(old)


def test_enheter_raknar_upp_alla_utgangar_och_ingangar():
    """Utan NOTAT_SINK/NOTAT_SOURCE ska varje utgång och ingång fångas."""
    old = os.environ.pop("NOTAT_SINK", None), os.environ.pop("NOTAT_SOURCE", None)
    try:
        tracks = notat.device_list()
    finally:
        if old[0] is not None:
            os.environ["NOTAT_SINK"] = old[0]
        if old[1] is not None:
            os.environ["NOTAT_SOURCE"] = old[1]
    assert tracks, "inga enheter"
    ut = [t for t in tracks if t[0] == "ut"]
    in_ = [t for t in tracks if t[0] == "in"]
    assert ut and in_, (ut, in_)
    assert all(t[1].endswith(".monitor") for t in ut), ut     # utgång läses som monitor
    assert not any(".monitor" in t[1] for t in in_), in_      # monitor är ingen mikrofon
    assert all(t[2] in ("Mötet", "Du") for t in tracks), tracks


def test_chunks_delar_pa_styckegrans_utan_att_tappa_text():
    text = "\n\n".join("x" * 900 for _ in range(20))      # ~18 000 tecken
    delar = notat.chunks(text, size=16000)
    assert len(delar) >= 2, len(delar)
    assert "".join(delar).count("x") == text.count("x"), "text tappades i delningen"


def test_summarize_ger_fel_utan_att_kasta():
    old = os.environ.get("NOTAT_AI_ENDPOINT")
    os.environ["NOTAT_AI_ENDPOINT"] = "http://127.0.0.1:1/v1"   # stängd port
    try:
        txt, err = notat.summarize("Hej. " * 50)
        assert txt is None and err, (txt, err)
    finally:
        os.environ.pop("NOTAT_AI_ENDPOINT", None)
        if old is not None:
            os.environ["NOTAT_AI_ENDPOINT"] = old


def test_ai_config_foljer_omascribe():
    endpoint, key, model = notat.ai_config()
    assert endpoint.startswith("http"), endpoint
    assert model, "modell saknas"


def _kuvert(mönster, förskjutning=0, skala=1.0):
    """Testhjälp: kuvert i stil med envelope() - 20 ms per värde."""
    svans = [0.0] * 60
    return ([0.0] * förskjutning + [v * skala for v in mönster] + svans, 0.02)


def _mönster(n=300):
    return [1000 * abs(__import__("math").sin(i / 7)) + (i % 13) for i in range(n)]


def test_dedupe_slar_ihop_samma_ljud_fran_flera_enheter():
    """Samma ljud på två enheter: behåll den starkaste, oavsett vad whisper skrev."""
    m = _mönster()
    envs = {1: _kuvert(m), 2: _kuvert(m, förskjutning=5, skala=0.3)}
    p = [0.0, 5.0, "Mötet#1", "Vi börjar om den här kursen och det kommer inte att vara så."]
    q = [0.0, 5.0, "Du#2", "Någonting i början av kursen att det inte kommer vara mer för läsning."]
    r = [0.0, 5.0, "Du#3", "Helt annat ljud som ingen annan enhet hörde, om dagboken och systemet."]
    envs[3] = _kuvert([500 * abs(__import__("math").cos(i / 3)) for i in range(300)])
    kvar = notat.dedupe([p, q, r], envs)
    assert len(kvar) == 2, kvar
    assert kvar[0][2] == "Mötet#1", kvar          # den starkaste kopian vann
    assert kvar[1][2] == "Du#3", kvar             # olikt ljud behålls


def test_dedupe_ror_inte_olika_ljud_samtidigt():
    """Två personer samtidigt på olika enheter ska båda vara kvar."""
    envs = {1: _kuvert(_mönster()), 2: _kuvert([300 * ((i * 7) % 11) for i in range(300)])}
    a = [0.0, 5.0, "Mötet#1", "Vi går vidare med händelsedriven arkitektur i stället för lager."]
    b = [0.5, 4.0, "Du#2", "Kan vi använda samma databas för båda tjänsterna eller dela den?"]
    assert len(notat.dedupe([a, b], envs)) == 2


def test_korr_hittar_forskjutningen():
    m = _mönster()
    assert notat.korr(m, [0.0] * 5 + m[:295]) > 0.9
    olika = [(i * 7919) % 1000 for i in range(300)]
    assert notat.korr(m, olika) < 0.5, notat.korr(m, olika)
    assert notat.korr([0.0] * 300, [0.0] * 300) == 0.0


def test_eko_varningen_tander_bara_nar_utgangen_hors_i_micken():
    m = _mönster()
    envs = {1: _kuvert(m), 2: _kuvert(m, förskjutning=3, skala=0.5)}
    spårtyp = {1: "ut", 2: "in"}
    mic = [0.0, 5.0, "Du#2", "Det var väl med den andra kursen, det är det vi kör nu."]
    ut = [0.0, 5.0, "Mötet#1", "Någonting i början av kursen att det inte kommer vara mer."]
    träffar, antal = notat.eko_stycken([mic, ut], envs, spårtyp)
    assert (träffar, antal) == (1, 1), (träffar, antal)
    # olika ljud samtidigt: ingen varning, och stycket behålls
    envs[2] = _kuvert([300 * ((i * 7) % 11) for i in range(300)])
    assert notat.eko_stycken([mic, ut], envs, spårtyp) == (0, 1)
    assert len(notat.dedupe([mic, ut], envs)) == 2
    # diariseringen kan ha döpt om talaren - spårnumret avgör, inte namnet
    omdöpt = [0.0, 5.0, "Deltagare 1#1", "Någonting i början av kursen."]
    assert notat.eko_stycken([mic, omdöpt], envs, spårtyp) == (0, 1)


def test_uteslutning_fran_config():
    """Webkameramiken ska kunna stängas av i config - och finnas där utan config."""
    def spår_med(cfg):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(cfg, f)
            path = f.name
        gammal, notat.CONFIG = notat.CONFIG, path
        notat.UTESLUTNA.clear()
        try:
            return notat.device_list(), list(notat.UTESLUTNA)
        finally:
            notat.CONFIG = gammal
            os.unlink(path)

    med, uteslutna = spår_med({"uteslut": ["WCAM110BK"]})
    assert not any("WCAM" in f"{t[1]} {t[3]}" for t in med), med
    assert any("WCAM" in u for u in uteslutna), uteslutna
    utan, _ = spår_med({"uteslut": []})
    assert any("WCAM" in f"{t[1]} {t[3]}" for t in utan), utan     # annars vore provet tomt


def test_valj_slar_av_och_pa_en_enhet():
    """Väljaren i baren skriver till config - och av/på måste gå att vända."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"uteslut": ["provsink"]}, f)
        path = f.name
    gammal, notat.CONFIG = notat.CONFIG, path
    try:
        alla = notat.enheter_alla()
        d = next((x for x in alla if "hdmi" in x["nod"]), None)
        assert d is not None, "hittar ingen hdmi-enhet att prova med"
        assert d["vald"] is True, d

        assert notat.cmd_valj({"_": [d["nod"]]}) == 0          # slå av
        d2 = next(x for x in notat.enheter_alla() if x["nod"] == d["nod"])
        assert d2["vald"] is False, d2
        assert not any(t[1] == d["nod"] for t in notat.device_list()), "utesluten enhet valdes ändå"

        assert notat.cmd_valj({"_": [d["nod"]]}) == 0          # slå på igen
        d3 = next(x for x in notat.enheter_alla() if x["nod"] == d["nod"])
        assert d3["vald"] is True, d3
        assert any(t[1] == d["nod"] for t in notat.device_list())

        assert notat.cmd_valj({"_": ["finns-inte"]}) == 1      # okänd enhet ska inte tysta skriva
        assert notat.cmd_valj({"_": []}) == 0                  # notat valj alla
        assert notat.notat_config().get("uteslut") == [], notat.notat_config()
    finally:
        notat.CONFIG = gammal
        os.unlink(path)


def test_modellkatalog_val_och_nedladdning():
    """Barens modellmeny: katalogen, valet, och vägran när filen inte finns."""
    import shutil
    tmp = tempfile.mkdtemp()
    rot = os.path.join(tmp, "modeller")
    os.makedirs(os.path.join(rot, "kb-whisper-large"))
    with open(os.path.join(rot, "kb-whisper-large", "ggml-model.bin"), "wb") as f:
        f.write(b"x")
    cfgp = os.path.join(tmp, "config.json")
    with open(cfgp, "w", encoding="utf-8") as f:
        json.dump({}, f)
    gammal_rot, gammal_cfg = notat.MODEL_ROOT, notat.CONFIG
    notat.MODEL_ROOT, notat.CONFIG = rot, cfgp
    try:
        for m in notat.MODELLER:      # en trasig rad i katalogen = död nedladdningsknapp
            assert m["url"].startswith("https://") and m["url"].endswith(".bin"), m
            assert m["fil"].endswith(".bin") and m["mb"] > 0 and m["namn"], m
        kat = {m["id"]: m for m in notat.modell_katalog()}
        assert kat["kb-whisper-large"]["finns"] is True, kat["kb-whisper-large"]
        assert kat["kb-whisper-small"]["finns"] is False, kat["kb-whisper-small"]

        assert notat.cmd_modell({"_": ["kb-whisper-small"]}) == 1      # inte nedladdad
        assert notat.notat_config().get("modell") in (None, ""), "valde en modell som saknas"
        assert notat.cmd_modell({"_": ["finns-inte"]}) == 1            # okänt id

        assert notat.cmd_modell({"_": ["kb-whisper-large"]}) == 0
        assert notat.notat_config()["modell"] == "kb-whisper-large"
        assert notat.find_model() == os.path.join(rot, "kb-whisper-large", "ggml-model.bin")
        assert kat["kb-whisper-large"]["sökväg"]
        assert notat.modell_namn(notat.find_model()) == "kb-whisper-large"

        assert notat.cmd_hamta({"_": ["kb-whisper-large"]}) == 0       # redan hemma
        assert notat.cmd_hamta({"_": ["finns-inte"]}) == 1             # inget nätanrop
    finally:
        notat.MODEL_ROOT, notat.CONFIG = gammal_rot, gammal_cfg
        shutil.rmtree(tmp)


def test_modellernas_url_ger_en_fil():
    """Nätprov (NOTAT_NATVERK=1): varje nedladdningsknapp måste peka på en riktig fil."""
    if os.environ.get("NOTAT_NATVERK") != "1":
        return
    import urllib.request
    for m in notat.MODELLER:
        req = urllib.request.Request(m["url"], method="HEAD",
                                     headers={"User-Agent": "notat/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            mb = int(r.headers.get("Content-Length") or 0) >> 20
            assert r.status == 200 and mb > 100, f"{m['id']}: {r.status} {mb} MB"
            assert abs(mb - m["mb"]) < max(200, m["mb"] * 0.3), f"{m['id']}: katalogen säger {m['mb']} MB, filen är {mb} MB"


def test_talaretiketter_och_tilldelning():
    """Diarisering -> etiketter: mest talför först, och mikrofonens spår blir 'Du'."""
    turer = [(0, 10, "speaker_01"), (10, 14, "speaker_00"), (14, 40, "speaker_01")]
    m = notat.diar_etiketter(turer)
    assert m == {"speaker_01": "Deltagare 1", "speaker_00": "Deltagare 2"}, m
    m2 = notat.diar_etiketter(turer, bas=2)          # två spår får inte samma nummer
    assert m2["speaker_01"] == "Deltagare 3" and m2["speaker_00"] == "Deltagare 4", m2
    m3 = notat.diar_etiketter(turer, dominant="Du")
    assert m3["speaker_01"] == "Du" and m3["speaker_00"] == "Deltagare 1", m3

    assert notat.talare_vid(turer, m, 1.0, 9.0) == "Deltagare 1"      # störst överlapp vinner
    assert notat.talare_vid(turer, m, 10.5, 13.0) == "Deltagare 2"
    assert notat.talare_vid([(0, 1, "speaker_00")], m, 100.0, 104.0) is None   # ingen gissning

    # märkningen sker per segment och spårnumret behålls - dubblett- och ekologiken
    # hänger på numret, inte på talarens namn
    segs = [(1.0, 9.0, "Mötet#1", "hej"), (10.5, 13.0, "Mötet#1", "där"),
            (60.0, 64.0, "Mötet#1", "utanför diariseringen")]
    ut = notat.märk_segment(segs, turer, m)
    assert [s[2] for s in ut] == ["Deltagare 1#1", "Deltagare 2#1", "Mötet#1"], ut
    assert ut[0][3] == "hej" and ut[0][0] == 1.0, ut[0]          # text och tider orörda


def test_roster_vaxeln_och_vagran():
    """Röstväxeln skriver config, vägrar slås på utan modeller, och hämtar inte i onödan."""
    import shutil
    tmp = tempfile.mkdtemp()
    cfgp = os.path.join(tmp, "config.json")
    with open(cfgp, "w", encoding="utf-8") as f:
        json.dump({}, f)
    gammal_cfg, gammal_filer = notat.CONFIG, notat.DIAR_FILER
    notat.CONFIG = cfgp
    try:
        notat.DIAR_FILER = [{"klar": os.path.join(tmp, "saknas"), "nm": "x", "mb": 1}]
        assert notat.diar_finns() is False
        assert notat.cmd_röster({"_": ["på"]}) == 1
        assert notat.notat_config().get("röster") in (None, False), "slog på utan modeller"
        assert notat.cmd_röster({"_": ["av"]}) == 0
        assert notat.cmd_röster({"_": ["kanske"]}) == 1, "okänt läge ska vägras"

        klar = os.path.join(tmp, "modell"); open(klar, "w").close()
        notat.DIAR_FILER = [{"klar": klar, "nm": "x", "mb": 1}]
        assert notat.diar_finns() is True
        assert notat.cmd_röster({"_": ["på"]}) == 0
        assert notat.notat_config()["röster"] is True
        assert notat.röster_på() is True
        assert notat.cmd_diar_hamta({"_": []}) == 0, "ska inte ladda ner när allt finns"
    finally:
        notat.CONFIG, notat.DIAR_FILER = gammal_cfg, gammal_filer
        shutil.rmtree(tmp)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"ok   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} ok")
    sys.exit(1 if failed else 0)
