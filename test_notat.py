#!/usr/bin/env python3
"""Kontroller av notat:s logik som inte kräver ljudenheter.

  python3 test_notat.py     (0 = allt ok)
"""
import importlib.util
import os
import sys

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


def test_dedupe_slar_ihop_samma_mening_fran_flera_enheter():
    """Verkliga rader ur en körning: två mikrofoner + en utgång med samma mening."""
    backlogg = [0.0, 5.0, "Mötet#4",
                "mer i vår backlogg så att vi har mer att jobba på. Sedan från backloggen så gör du en ny "
                "sprintlogg av de viktigaste punkterna som är högst prioriterade först."]
    mic1 = [0.0, 5.0, "Du#5",
            "ner i vår backlogg så att vi har mer att uppa på. Sedan från backloggen så gör vi en ny sprintlogg "
            "av de viktigaste punkterna som högt prioriterade först."]
    mic2 = [0.0, 5.0, "Du#6",
            "så att vi har mer att jobba på. Sedan från backlagen så gör ni sprintlag av de viktigaste "
            "punkterna som är högst prioriterade först."]
    annan = [3.0, 6.0, "Mötet#4", "Förläsningen handlar om systemarkitektur och tentan är den 12 december."]
    # mikrofonkopiorna börjar tidigast - utgången ska ändå vinna
    kvar = notat.dedupe([mic1, mic2, backlogg, annan])
    assert len(kvar) == 2, kvar
    assert kvar[0][2] == "Mötet#4" and "backlogg" in kvar[0][3], kvar   # utgången vann
    assert kvar[1][3].startswith("Förläsningen"), kvar


def test_dedupe_ror_inte_ett_samtal():
    """Två personer samtidigt (olika text, samma tid) ska båda vara kvar."""
    a = [0.0, 5.0, "Mötet#1", "Vi går vidare med händelsedriven arkitektur i stället för lager på lager."]
    b = [0.5, 4.0, "Du#2", "Kan vi använda samma databas för båda tjänsterna eller måste vi dela upp den?"]
    assert len(notat.dedupe([a, b])) == 2


def test_dedupe_ror_inte_korta_inpass():
    a = [0.0, 5.0, "Mötet#1", "Ja precis."]
    b = [1.0, 4.0, "Du#2", "Ja precis."]
    assert len(notat.dedupe([a, b])) == 2, "korta svar ska inte slås ihop"


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
