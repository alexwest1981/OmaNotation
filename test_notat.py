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
    env = dict(os.environ, NOTAT_SINK="notat_test.monitor", NOTAT_SOURCE="mic")
    old = os.environ.copy()
    os.environ.update(env)
    try:
        remote, source = notat.devices()
        assert remote == "notat_test.monitor", remote
        assert source == "mic", source
    finally:
        os.environ.clear()
        os.environ.update(old)


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
