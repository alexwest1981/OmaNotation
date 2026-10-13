#!/usr/bin/env python3
"""Checks of notat's logic that do not require audio devices.

  python3 test_notat.py     (0 = everything ok)
"""
import base64
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_loader("notat", importlib.machinery.SourceFileLoader("notat", os.path.join(HERE, "notat")))
notat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notat)


def test_segments_skip_noise():
    data = {"transcription": [
        {"offsets": {"from": 0, "to": 2000}, "text": " Hej och välkomna till föreläsningen. "},
        {"offsets": {"from": 2000, "to": 3000}, "text": ""},
        {"offsets": {"from": 3000, "to": 4000}, "text": "[Musik]"},
        {"offsets": {"from": 4000, "to": 5000}, "text": " (musik spelas) "},
        {"offsets": {"from": 5000, "to": 6000}, "text": "Tentan är den tolfte."},
    ]}
    segs = notat.segments(data, "Meeting")
    assert [s[3] for s in segs] == ["Hej och välkomna till föreläsningen.", "Tentan är den tolfte."], segs
    assert segs[0][0] == 0.0 and segs[1][0] == 5.0, segs        # offset in ms -> seconds


def test_paragraphs_join_same_speaker():
    segs = [(0, 2, "Meeting", "Hej"), (2.5, 4, "Meeting", "allihop"), (10, 12, "You", "Hej själv"),
            (12.1, 13, "You", "tack"), (14, 15, "Meeting", "Bra")]
    paras = notat.paragraphs(segs)
    assert [p[2] for p in paras] == ["Meeting", "You", "Meeting"], paras
    assert paras[0][3] == "Hej allihop", paras          # < 3 s apart -> same paragraph
    assert paras[1][3] == "Hej själv tack", paras
    assert paras[2][3] == "Bra", paras


def test_paragraphs_break_long_paragraphs():
    segs = [(i, i + 1, "Meeting", "x" * 250) for i in range(4)]
    assert len(notat.paragraphs(segs, maxlen=400)) > 1


def test_paragraphs_sorted_by_both_tracks():
    remote = [(5.0, 7.0, "Meeting", "fråga")]
    mic = [(0.5, 3.0, "You", "svar")]
    assert [s[2] for s in sorted(remote + mic, key=lambda s: s[0])] == ["You", "Meeting"]


def test_mmss():
    assert notat.mmss(0) == "00:00" and notat.mmss(3661) == "61:01"


def test_devices_require_monitor_suffix():
    # .monitor must not be doubled, and an explicit NOTAT_SINK wins
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


def test_devices_enumerate_all_outputs_and_inputs():
    """Without NOTAT_SINK/NOTAT_SOURCE every output and every input must be captured."""
    old = os.environ.pop("NOTAT_SINK", None), os.environ.pop("NOTAT_SOURCE", None)
    try:
        tracks = notat.device_list()
    finally:
        if old[0] is not None:
            os.environ["NOTAT_SINK"] = old[0]
        if old[1] is not None:
            os.environ["NOTAT_SOURCE"] = old[1]
    assert tracks, "no devices"
    out = [t for t in tracks if t[0] == "out"]
    in_ = [t for t in tracks if t[0] == "in"]
    assert out and in_, (out, in_)
    assert all(t[1].endswith(".monitor") for t in out), out    # an output is read as a monitor
    assert not any(".monitor" in t[1] for t in in_), in_       # a monitor is not a microphone
    assert all(t[2] in ("Meeting", "You") for t in tracks), tracks


def test_chunks_split_on_paragraph_boundary_without_losing_text():
    text = "\n\n".join("x" * 900 for _ in range(20))      # ~18 000 characters
    parts = notat.chunks(text, size=16000)
    assert len(parts) >= 2, len(parts)
    assert "".join(parts).count("x") == text.count("x"), "text was lost in the split"


def test_summarize_returns_error_without_throwing():
    old = os.environ.get("NOTAT_AI_ENDPOINT")
    os.environ["NOTAT_AI_ENDPOINT"] = "http://127.0.0.1:1/v1"   # closed port
    try:
        txt, err = notat.summarize("Hej. " * 50)
        assert txt is None and err, (txt, err)
    finally:
        os.environ.pop("NOTAT_AI_ENDPOINT", None)
        if old is not None:
            os.environ["NOTAT_AI_ENDPOINT"] = old


def test_ai_config_follows_omascribe():
    """The AI settings are read from OmaScribe's config - give it one instead of the machine's."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"ai_endpoint": "http://127.0.0.1:1/v1", "ai_model": "test-model"}, f)
        path = f.name
    old_cfg, notat.OMASCRIBE_CFG = notat.OMASCRIBE_CFG, path
    old_env = {k: os.environ.pop(k, None) for k in ("NOTAT_AI_ENDPOINT", "NOTAT_AI_MODEL", "NOTAT_AI_KEY")}
    try:
        endpoint, _, model = notat.ai_config()
        assert endpoint == "http://127.0.0.1:1/v1", endpoint
        assert model == "test-model", model
    finally:
        notat.OMASCRIBE_CFG = old_cfg
        os.unlink(path)
        for k, v in old_env.items():
            if v is not None:
                os.environ[k] = v


def _envelope(pattern, offset=0, scale=1.0):
    """Test helper: an envelope in the style of envelope() - 20 ms per value."""
    tail = [0.0] * 60
    return ([0.0] * offset + [v * scale for v in pattern] + tail, 0.02)


def _pattern(n=300):
    return [1000 * abs(__import__("math").sin(i / 7)) + (i % 13) for i in range(n)]


def test_dedupe_merges_same_audio_from_several_devices():
    """Same audio on two devices: keep the strongest, whatever whisper wrote."""
    m = _pattern()
    envs = {1: _envelope(m), 2: _envelope(m, offset=5, scale=0.3)}
    p = [0.0, 5.0, "Meeting#1", "Vi börjar om den här kursen och det kommer inte att vara så."]
    q = [0.0, 5.0, "You#2", "Någonting i början av kursen att det inte kommer vara mer för läsning."]
    r = [0.0, 5.0, "You#3", "Helt annat ljud som ingen annan enhet hörde, om dagboken och systemet."]
    envs[3] = _envelope([500 * abs(__import__("math").cos(i / 3)) for i in range(300)])
    kept = notat.dedupe([p, q, r], envs)
    assert len(kept) == 2, kept
    assert kept[0][2] == "Meeting#1", kept          # the strongest copy won
    assert kept[1][2] == "You#3", kept              # different audio is kept


def test_dedupe_finds_duplicate_even_when_paragraph_boundaries_differ():
    """The paragraph boundaries slide between devices: whisper placed the same sentence at 46-48 s on one
    track and 48-52 s on the other (measured in a real run). Comparing only the time both
    *claimed* to cover gave 0.57 and the duplicate slipped through."""
    m = _pattern(4000)
    envs = {1: _envelope(m), 2: _envelope(m, scale=0.4)}
    p = [46.0, 48.0, "Meeting#1", "Hem, men blir inte svårt att testa då."]
    q = [48.0, 52.0, "You#2", "Men blir inte svårt att testa då. Vi kanske ska köra händelser."]
    kept = notat.dedupe([p, q], envs)
    assert len(kept) == 1, kept
    assert kept[0][2] == "Meeting#1", kept          # the strongest copy (1.0 vs 0.4) is kept


def test_dedupe_does_not_merge_different_times_despite_same_audio():
    """The trap that killed the first attempt: when both tracks carry the same audio, *any*
    common window correlates (measured 0.99 even for paragraphs 20 s apart). The comparison window
    must be the one device's own, otherwise the whole meeting is merged."""
    m = _pattern(4000)
    envs = {1: _envelope(m), 2: _envelope(m, scale=0.4)}
    p = [10.0, 14.0, "Meeting#1", "Då tar jag gränssnittet och testerna."]
    q = [30.0, 34.0, "You#2", "Just det, en sak till om kravspecifikationen."]
    kept = notat.dedupe([p, q], envs)
    assert len(kept) == 2, kept


def test_dedupe_does_not_touch_different_audio_at_the_same_time():
    """Two people at the same time on different devices must both stay."""
    envs = {1: _envelope(_pattern()), 2: _envelope([300 * ((i * 7) % 11) for i in range(300)])}
    a = [0.0, 5.0, "Meeting#1", "Vi går vidare med händelsedriven arkitektur i stället för lager."]
    b = [0.5, 4.0, "You#2", "Kan vi använda samma databas för båda tjänsterna eller dela den?"]
    assert len(notat.dedupe([a, b], envs)) == 2


def test_korr_finds_the_offset():
    m = _pattern()
    assert notat.korr(m, [0.0] * 5 + m[:295]) > 0.9
    different = [(i * 7919) % 1000 for i in range(300)]
    assert notat.korr(m, different) < 0.5, notat.korr(m, different)
    assert notat.korr([0.0] * 300, [0.0] * 300) == 0.0


def test_echo_warning_only_lights_up_when_the_output_is_heard_in_the_mic():
    m = _pattern()
    envs = {1: _envelope(m), 2: _envelope(m, offset=3, scale=0.5)}
    track_kind = {1: "out", 2: "in"}
    mic = [0.0, 5.0, "You#2", "Det var väl med den andra kursen, det är det vi kör nu."]
    out = [0.0, 5.0, "Meeting#1", "Någonting i början av kursen att det inte kommer vara mer."]
    hits, count = notat.echo_paragraphs([mic, out], envs, track_kind)
    assert (hits, count) == (1, 1), (hits, count)
    # different audio at the same time: no warning, and the paragraph is kept
    envs[2] = _envelope([300 * ((i * 7) % 11) for i in range(300)])
    assert notat.echo_paragraphs([mic, out], envs, track_kind) == (0, 1)
    assert len(notat.dedupe([mic, out], envs)) == 2
    # the diarisation may have renamed the speaker - the track number decides, not the name
    renamed = [0.0, 5.0, "Speaker 1#1", "Någonting i början av kursen."]
    assert notat.echo_paragraphs([mic, renamed], envs, track_kind) == (0, 1)


def test_exclusion_from_config():
    """The webcam mic must be possible to turn off in config - and be there without config."""
    def tracks_with(cfg):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(cfg, f)
            path = f.name
        old, notat.CONFIG = notat.CONFIG, path
        notat.EXCLUDED.clear()
        try:
            return notat.device_list(), list(notat.EXCLUDED)
        finally:
            notat.CONFIG = old
            os.unlink(path)

    picked, excluded = tracks_with({"exclude": ["WCAM110BK"]})
    assert not any("WCAM" in f"{t[1]} {t[3]}" for t in picked), picked
    assert any("WCAM" in u for u in excluded), excluded
    without, _ = tracks_with({"exclude": []})
    assert any("WCAM" in f"{t[1]} {t[3]}" for t in without), without     # otherwise the test would be empty


def test_select_turns_a_device_off_and_on():
    """The bar's selector writes to config - and off/on must be reversible."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"exclude": ["testsink"]}, f)
        path = f.name
    old, notat.CONFIG = notat.CONFIG, path
    try:
        every = notat.all_devices()
        d = next((x for x in every if "hdmi" in x["node"]), None)
        assert d is not None, "found no hdmi device to test with"
        assert d["selected"] is True, d

        assert notat.cmd_select({"_": [d["node"]]}) == 0          # turn off
        d2 = next(x for x in notat.all_devices() if x["node"] == d["node"])
        assert d2["selected"] is False, d2
        assert not any(t[1] == d["node"] for t in notat.device_list()), "excluded device was selected anyway"

        assert notat.cmd_select({"_": [d["node"]]}) == 0          # turn on again
        d3 = next(x for x in notat.all_devices() if x["node"] == d["node"])
        assert d3["selected"] is True, d3
        assert any(t[1] == d["node"] for t in notat.device_list())

        assert notat.cmd_select({"_": ["does-not-exist"]}) == 1      # an unknown device must not write silently
        assert notat.cmd_select({"_": []}) == 0                  # notat select all
        assert notat.notat_config().get("exclude") == [], notat.notat_config()
    finally:
        notat.CONFIG = old
        os.unlink(path)


def test_model_catalog_choice_and_download():
    """The bar's model menu: the catalogue, the choice, and the refusal when the file is missing."""
    import shutil
    tmp = tempfile.mkdtemp()
    root = os.path.join(tmp, "models")
    os.makedirs(os.path.join(root, "kb-whisper-large"))
    with open(os.path.join(root, "kb-whisper-large", "ggml-model.bin"), "wb") as f:
        f.write(b"x")
    cfgp = os.path.join(tmp, "config.json")
    with open(cfgp, "w", encoding="utf-8") as f:
        json.dump({}, f)
    old_root, old_cfg = notat.MODEL_ROOT, notat.CONFIG
    notat.MODEL_ROOT, notat.CONFIG = root, cfgp
    try:
        for m in notat.MODELS:      # a broken row in the catalogue = a dead download button
            assert m["url"].startswith("https://") and m["url"].endswith(".bin"), m
            assert m["file"].endswith(".bin") and m["mb"] > 0 and m["name"], m
        cat = {m["id"]: m for m in notat.model_catalog()}
        assert cat["kb-whisper-large"]["downloaded"] is True, cat["kb-whisper-large"]
        assert cat["kb-whisper-small"]["downloaded"] is False, cat["kb-whisper-small"]

        assert notat.cmd_model({"_": ["kb-whisper-small"]}) == 1      # not downloaded
        assert notat.notat_config().get("model") in (None, ""), "selected a model that is missing"
        assert notat.cmd_model({"_": ["does-not-exist"]}) == 1        # unknown id

        assert notat.cmd_model({"_": ["kb-whisper-large"]}) == 0
        assert notat.notat_config()["model"] == "kb-whisper-large"
        assert notat.find_model() == os.path.join(root, "kb-whisper-large", "ggml-model.bin")
        assert cat["kb-whisper-large"]["path"]
        assert notat.model_name(notat.find_model()) == "kb-whisper-large"

        assert notat.cmd_download({"_": ["kb-whisper-large"]}) == 0       # already home
        assert notat.cmd_download({"_": ["does-not-exist"]}) == 1         # no network call
    finally:
        notat.MODEL_ROOT, notat.CONFIG = old_root, old_cfg
        shutil.rmtree(tmp)


def test_model_urls_resolve_to_a_file():
    """Network test (NOTAT_NETWORK=1): every download button must point at a real file."""
    if os.environ.get("NOTAT_NETWORK") != "1":
        return
    import urllib.request
    for m in notat.MODELS:
        req = urllib.request.Request(m["url"], method="HEAD",
                                     headers={"User-Agent": "notat/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            mb = int(r.headers.get("Content-Length") or 0) >> 20
            assert r.status == 200 and mb > 100, f"{m['id']}: {r.status} {mb} MB"
            assert abs(mb - m["mb"]) < max(200, m["mb"] * 0.3), f"{m['id']}: the catalogue says {m['mb']} MB, the file is {mb} MB"


def test_speaker_labels_and_assignment():
    """Diarisation -> labels: the most talkative first, and the microphone's track becomes 'You'."""
    turns = [(0, 10, "speaker_01"), (10, 14, "speaker_00"), (14, 40, "speaker_01")]
    m = notat.diar_labels(turns)
    assert m == {"speaker_01": "Speaker 1", "speaker_00": "Speaker 2"}, m
    m2 = notat.diar_labels(turns, base=2)          # two tracks must not get the same number
    assert m2["speaker_01"] == "Speaker 3" and m2["speaker_00"] == "Speaker 4", m2
    m3 = notat.diar_labels(turns, dominant="You")
    assert m3["speaker_01"] == "You" and m3["speaker_00"] == "Speaker 1", m3

    assert notat.speaker_at(turns, m, 1.0, 9.0) == "Speaker 1"      # the largest overlap wins
    assert notat.speaker_at(turns, m, 10.5, 13.0) == "Speaker 2"
    assert notat.speaker_at([(0, 1, "speaker_00")], m, 100.0, 104.0) is None   # no guessing

    # the labelling happens per segment and the track number is kept - the duplicate and echo
    # logic hangs on the number, not on the speaker's name
    segs = [(1.0, 9.0, "Meeting#1", "hej"), (10.5, 13.0, "Meeting#1", "där"),
            (60.0, 64.0, "Meeting#1", "utanför diariseringen")]
    out = notat.label_segments(segs, turns, m)
    assert [s[2] for s in out] == ["Speaker 1#1", "Speaker 2#1", "Meeting#1"], out
    assert out[0][3] == "hej" and out[0][0] == 1.0, out[0]          # text and times untouched


def test_voice_switch_and_refusal():
    """The voice switch writes config, refuses to turn on without models, and does not fetch needlessly."""
    import shutil
    tmp = tempfile.mkdtemp()
    cfgp = os.path.join(tmp, "config.json")
    with open(cfgp, "w", encoding="utf-8") as f:
        json.dump({}, f)
    old_cfg, old_files = notat.CONFIG, notat.DIAR_FILES
    notat.CONFIG = cfgp
    try:
        notat.DIAR_FILES = [{"ready": os.path.join(tmp, "missing"), "name": "x", "mb": 1,
                             "dest": os.path.join(tmp, "x"), "parts": []}]
        assert notat.diar_available() is False
        assert notat.cmd_speakers({"_": ["on"]}) == 1
        assert notat.notat_config().get("speakers") in (None, False), "turned on without models"
        assert notat.cmd_speakers({"_": ["off"]}) == 0
        assert notat.cmd_speakers({"_": ["maybe"]}) == 1, "an unknown mode must be refused"

        ready = os.path.join(tmp, "model"); open(ready, "w").close()
        notat.DIAR_FILES = [{"ready": ready, "name": "x", "mb": 1,
                             "dest": os.path.join(tmp, "x"), "parts": []}]
        assert notat.diar_available() is True
        assert notat.cmd_speakers({"_": ["on"]}) == 0
        assert notat.notat_config()["speakers"] is True
        assert notat.speakers_enabled() is True
        assert notat.cmd_diar_download({"_": []}) == 0, "must not download when everything is there"
    finally:
        notat.CONFIG, notat.DIAR_FILES = old_cfg, old_files
        shutil.rmtree(tmp)


def test_status_reports_running_transcription():
    """The bar reads the job from a file, not from QML memory.

    Reloading the widget clears the memory — so status must be able to say
    "transcribing" afterwards, and a dead child must not leave a lie behind.
    """
    import contextlib
    import io
    import subprocess
    old = (notat.STATE, notat.SESSION, notat.JOB)
    with tempfile.TemporaryDirectory() as d:
        notat.STATE = d
        notat.SESSION = os.path.join(d, "session.json")
        notat.JOB = os.path.join(d, "transcription.json")

        def status():
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                notat.cmd_status({"json": True})
            return json.loads(buf.getvalue())

        try:
            assert status()["transcribing"] is False, "no job = not transcribing"

            notat.job_write(os.getpid(), "/tmp/recording", 1741)
            s = status()
            assert s["transcribing"] is True and s["transcribing_dir"] == "/tmp/recording", s
            assert s["transcribing_seconds"] >= 0, s

            dead = subprocess.Popen(["true"])
            dead.wait()                                   # reaped child = dead pid
            notat.job_write(dead.pid, "/tmp/recording", 1741)
            assert status()["transcribing"] is False, "a dead child must not look like a job"
            assert not os.path.exists(notat.JOB), "dead jobs must be cleaned up"

            notat.job_clear()
            assert status()["transcribing"] is False
        finally:
            notat.STATE, notat.SESSION, notat.JOB = old


def test_speaker_list_only_shows_voices_in_the_text():
    """The header must match the text: labels that vanished with the duplicates
    must not be listed as participants."""
    paras = [(0, 1, "You#5", "hej"), (1, 2, "Speaker 1#2", "hallå"),
             (2, 3, "Meeting#1", "hm"), (3, 4, "Speaker 1#3", "igen")]
    assert notat.speakers_in_text(paras) == ["You", "Speaker 1"], notat.speakers_in_text(paras)
    assert notat.speakers_in_text([(0, 1, "Meeting#1", "bara mötet")]) == []


def test_names_on_speakers_do_not_touch_the_track_number():
    """A name only changes the label: who#nr carries the duplicate and echo logic."""
    labels = {"speaker_01": "Speaker 1", "speaker_00": "Speaker 2"}
    assert notat.rename_speakers(labels, None) == labels
    renamed = notat.rename_speakers(labels, {"Speaker 1": "Ada"})
    assert renamed == {"speaker_01": "Ada", "speaker_00": "Speaker 2"}, renamed
    assert notat.rename_speakers(labels, {"1": "Ada"})["speaker_01"] == "Ada"   # '1=Ada' too
    assert notat.rename_speakers(labels, {"Speaker 9": "Ada"}) == labels, "the wrong key changes nothing"
    assert notat.name_pairs("1=Ada, Speaker 2=Bo") == {"Speaker 1": "Ada", "Speaker 2": "Bo"}
    assert notat.name_pairs("junk") == {} and notat.name_pairs("1=") == {}

    segs = [(1.0, 9.0, "Meeting#2", "hej")]
    assert notat.label_segments(segs, [(0, 10, "speaker_01")], renamed)[0][2] == "Ada#2"


def test_meeting_gives_title_and_participants_in_the_document():
    """notat meeting -> session.json -> the document's heading. Without audio: the tracks are deliberately missing."""
    import shutil
    old = (notat.RAW_ROOT, notat.STATE, notat.SESSION, notat.JOB, notat.notify, notat.log)
    d = tempfile.mkdtemp()
    raw = os.path.join(d, "raw", "2026-10-06 09-00")
    os.makedirs(raw)
    tracks = [{"file": "out1.wav", "label": "Meeting", "desc": "speakers", "node": "x.monitor", "pid": 0},
              {"file": "in2.wav", "label": "You", "desc": "mic", "node": "y", "pid": 0}]
    with open(os.path.join(raw, "session.json"), "w", encoding="utf-8") as f:
        json.dump({"started": 1.0, "dir": raw, "pid": 0, "tracks": tracks}, f)
    notat.RAW_ROOT = os.path.join(d, "raw")
    notat.STATE = os.path.join(d, "state")
    os.makedirs(notat.STATE)
    notat.SESSION = os.path.join(notat.STATE, "session.json")
    notat.JOB = os.path.join(notat.STATE, "transcription.json")
    notat.notify = lambda *a, **k: None            # no desktop notification during the test
    notat.log = lambda *a, **k: None
    old_vault = os.environ.get("NOTAT_VAULT")
    try:
        assert notat.cmd_meeting({"_": ["Design review"], "participants": "Ada, Bo", "names": "1=Ada"}) == 0
        saved = json.load(open(os.path.join(raw, "session.json"), encoding="utf-8"))
        assert saved["title"] == "Design review", saved
        assert saved["participants"] == ["Ada", "Bo"], saved
        assert saved["names"] == {"Speaker 1": "Ada"}, saved
        assert saved["tracks"] == tracks, "the tracks must not be touched"
        assert not os.path.exists(os.path.join(raw, "session.json.del")), "temp file left behind"

        try:
            notat.find_model()
        except SystemExit:
            return                     # no whisper model -> the document cannot be built here
        os.environ["NOTAT_VAULT"] = os.path.join(d, "vault")
        path = notat.transcribe_dir(raw, 10, summary=False)
        text = open(path, encoding="utf-8").read()
        assert text.startswith("# Design review"), text[:200]
        assert "**Participants:** Ada · Bo" in text, text[:400]
        assert os.path.basename(path).startswith("Design review"), path
        assert not os.path.exists(path + ".del"), "temp file left behind after the document write"

        assert notat.cmd_meeting({"_": [], "clear": True}) == 0
        assert "title" not in json.load(open(os.path.join(raw, "session.json"), encoding="utf-8"))
    finally:
        if old_vault is None:
            os.environ.pop("NOTAT_VAULT", None)
        else:
            os.environ["NOTAT_VAULT"] = old_vault
        notat.RAW_ROOT, notat.STATE, notat.SESSION, notat.JOB, notat.notify, notat.log = old
        shutil.rmtree(d)


def test_voice_match_and_the_reference_file():
    """The voice registry: the right reference wins, doubt gives no name, and the file is written protected."""
    import shutil
    # two references (0-6 s = Ada, 7-13 s = Bo) and one unknown bit (14-20 s)
    windows = [(0.0, 6.0), (7.0, 13.0), (14.0, 20.0)]
    seg = [(0.0, 6.0, "speaker_00"), (7.0, 13.0, "speaker_01"), (14.0, 20.0, "speaker_00")]
    assert notat.voice_match(seg, windows) == 0, "same cluster as reference 0 -> Ada"
    seg[2] = (14.0, 20.0, "speaker_01")
    assert notat.voice_match(seg, windows) == 1
    seg[2] = (14.0, 20.0, "speaker_02")
    assert notat.voice_match(seg, windows) is None, "its own cluster -> no guessing"
    assert notat.voice_match([(0.0, 6.0, "speaker_00")], [(0.0, 6.0), (7.0, 13.0)]) is None

    tmp = tempfile.mkdtemp()
    old = notat.VOICE_ROOT
    notat.VOICE_ROOT = os.path.join(tmp, "voices")
    try:
        import math
        import wave
        silence = b"\x00\x00" * 16000 * 3
        tone = b"".join(int(12000 * math.sin(2 * math.pi * 220 * i / 16000)).to_bytes(2, "little", signed=True)
                        for i in range(16000 * 4))
        with_silence = os.path.join(tmp, "with_silence.wav")
        with wave.open(with_silence, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
            w.writeframes(silence + tone)
        assert notat.save_voice("Ada", with_silence) is True
        path = os.path.join(notat.VOICE_ROOT, "Ada.wav")
        assert os.path.exists(path) and os.stat(path).st_mode & 0o777 == 0o600, "the voice profile must be 0600"
        a, b = notat.best_clip(with_silence, notat.envelope(with_silence)[0])
        assert a >= 2.5, f"the silence must not become the voice profile (chose {a:.1f}s)"
        assert notat.references() == [("Ada", path)], notat.references()
        length = os.path.getsize(path)
        assert notat.save_voice("Ada", with_silence) is False, "a shorter sample must not overwrite"
        assert os.path.getsize(path) == length
        assert notat.cmd_forget({"_": ["Ada"]}) == 0 and not os.path.exists(path)
        assert notat.cmd_forget({"_": ["Ada"]}) == 1, "a removed voice must say so"
    finally:
        notat.VOICE_ROOT = old
        shutil.rmtree(tmp)


def test_search_and_latest_in_the_vault():
    """Search and latest against a temporary vault - rg is the tool, no index needed."""
    import shutil
    if not shutil.which("rg"):
        return                                # ripgrep missing -> the test cannot run
    old = notat.vault_root
    d = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(d, "Recordings"))
        older = os.path.join(d, "Recordings", "Meeting 2026-01-01 09-00.md")
        newer = os.path.join(d, "Recordings", "Meeting 2026-02-02 09-00.md")
        open(older, "w", encoding="utf-8").write("**[00:10] Ada:** mediator\n")
        open(newer, "w", encoding="utf-8").write("**[00:20] Bo:** annat\n")
        os.utime(older, (1_000_000, 1_000_000))
        notat.vault_root = lambda: d
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert notat.cmd_search({"_": ["mediator"]}) == 0
        assert "Ada" in buf.getvalue() and newer not in buf.getvalue(), buf.getvalue()
        with contextlib.redirect_stdout(io.StringIO()):
            assert notat.cmd_search({"_": ["not-here"]}) == 1, "no hit must say so"
        assert notat.latest_doc() == newer, "latest = most recently written"
        assert notat.cmd_latest({"_": []}) == 0
    finally:
        notat.vault_root = old
        shutil.rmtree(d)


def test_legacy_config_keys_carry_over_once():
    """A pre-1.2.0 config (Swedish keys) is read as the new one, and an empty new key must not
    shadow a set old one - the bar can write `exclude: []` before the file is ever rewritten."""
    import shutil
    d = tempfile.mkdtemp()
    path = os.path.join(d, "config.json")
    old = notat.CONFIG
    notat.CONFIG = path
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"uteslut": ["WCAM"], "röster": True, "modell": "kb-whisper-small",
                       "antal_talare": 3, "valv": "~/V"}, f)
        cfg = notat.notat_config()
        assert cfg["exclude"] == ["WCAM"] and cfg["speakers"] is True, cfg
        assert cfg["model"] == "kb-whisper-small", cfg
        assert cfg["speaker_count"] == 3 and cfg["vault"] == "~/V", cfg
        assert not any(k in cfg for k in notat.LEGACY_KEYS.values()), cfg   # one source of truth

        with open(path, "w", encoding="utf-8") as f:
            json.dump({"exclude": [], "uteslut": ["WCAM"]}, f)
        assert notat.notat_config()["exclude"] == ["WCAM"], "empty new key must not shadow the old"

        with open(path, "w", encoding="utf-8") as f:
            json.dump({"exclude": ["NEW"], "uteslut": ["WCAM"]}, f)
        assert notat.notat_config()["exclude"] == ["NEW"], "a set new key wins"
    finally:
        notat.CONFIG = old
        shutil.rmtree(d)


def test_every_download_carries_a_pinned_digest():
    """A download sink without a pinned sha256 is the finding the marketplace reported."""
    hex64 = re.compile(r"[0-9a-f]{64}")
    for m in notat.MODELS:
        assert hex64.fullmatch(m.get("sha256", "")), f"{m['id']} has no pinned digest"
    for f in notat.DIAR_FILES:
        assert hex64.fullmatch(f.get("sha256", "")), f"{f['name']} has no pinned digest"
        assert f["parts"], f"{f['name']} pins only the archive, not what is loaded"
        for path, digest in f["parts"]:
            assert hex64.fullmatch(digest), (f["name"], path)
        if f["tar"]:      # the archive's digest is not the digest of the files that run
            assert all(digest != f["sha256"] for _, digest in f["parts"]), f["name"]

    with open(os.path.join(HERE, "install.sh"), encoding="utf-8") as fh:
        installer = fh.read()
    assert hex64.fullmatch(re.search(r'VAD_SHA256="([^"]+)"', installer).group(1)), "install.sh"
    assert "sha256sum -c" in installer, "install.sh downloads the VAD model without checking it"


def test_a_download_that_does_not_match_is_rejected():
    """download_file checks the pinned digest and leaves nothing behind when it fails."""
    import shutil
    payload = b"notat" * 1000
    url = "data:application/octet-stream;base64," + base64.b64encode(payload).decode()
    digest = hashlib.sha256(payload).hexdigest()
    tmp = tempfile.mkdtemp()
    try:
        good = os.path.join(tmp, "artifact.bin")
        notat.download_file(url, good, min_mb=0, sha256=digest, what="artifact")
        assert os.path.getsize(good) == len(payload)
        bad = os.path.join(tmp, "artifact2.bin")
        try:
            notat.download_file(url, bad, min_mb=0, sha256="0" * 64, what="artifact")
            raise AssertionError("a download that does not match the pinned digest was accepted")
        except ValueError as e:
            assert "checksum" in str(e), e
        assert not os.path.exists(bad), "the rejected download was left on disk"
    finally:
        shutil.rmtree(tmp)


def test_a_tampered_diar_file_is_refused_before_it_runs():
    """The downloaded binary is checked against its pinned digest immediately before it runs."""
    import shutil
    tmp = tempfile.mkdtemp()
    sentinel = os.path.join(tmp, "ran")
    binp = os.path.join(tmp, "sherpa-onnx-offline-speaker-diarization")
    with open(binp, "w", encoding="utf-8") as f:
        f.write(f"#!/bin/sh\ntouch {sentinel}\n")
    os.chmod(binp, 0o755)
    digest = notat.sha256_file(binp)
    row = {"name": "sherpa-onnx", "tar": True, "ready": binp, "dest": tmp,
           "sha256": "a" * 64, "parts": [(binp, digest)]}
    old_files, old_log = notat.DIAR_FILES, notat.LOG
    notat.DIAR_FILES = [row]
    notat.LOG = os.path.join(tmp, "notat.log")
    try:
        assert notat.diar_intact(row) is True and notat.diar_verify() is None
        with open(binp, "a", encoding="utf-8") as f:
            f.write("# replaced after the download\n")
        assert notat.diar_intact(row) is False
        err = notat.diar_verify()
        assert err and "checksum" in err, err
        turns, err2 = notat.diar_turns(os.path.join(tmp, "audio.wav"))
        assert turns is None and err2 and "checksum" in err2, (turns, err2)
        assert not os.path.exists(sentinel), "the replaced binary was executed"
    finally:
        notat.DIAR_FILES, notat.LOG = old_files, old_log
        shutil.rmtree(tmp)


def test_pinned_digests_are_the_published_ones():
    """Network test (NOTAT_NETWORK=1): every pin is the digest the source itself publishes."""
    if os.environ.get("NOTAT_NETWORK") != "1":
        return
    import urllib.request

    def get_json(url):
        req = urllib.request.Request(url, headers={"User-Agent": "notat/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)

    def hf_published(url):
        """Hugging Face publishes each file's sha256 as the LFS oid."""
        repo, _, path = url.split("huggingface.co/")[1].partition("/resolve/main/")
        for e in get_json(f"https://huggingface.co/api/models/{repo}/tree/main?recursive=1"):
            if e.get("path") == path:
                return (e.get("lfs") or {}).get("oid")
        return None

    for m in notat.MODELS:
        assert hf_published(m["url"]) == m["sha256"], f"{m['id']}: the pin is not the published digest"
    for f in notat.DIAR_FILES:
        if "huggingface.co" in f["url"]:
            assert hf_published(f["url"]) == f["sha256"], f["name"]

    with open(os.path.join(HERE, "install.sh"), encoding="utf-8") as fh:
        installer = fh.read()
    assert hf_published(re.search(r'VAD_URL="([^"]+)"', installer).group(1)) == \
        re.search(r'VAD_SHA256="([^"]+)"', installer).group(1), "install.sh's VAD pin"

    # The sherpa-onnx release asset: GitHub reports the digest its uploader sent (sha256:<hex>).
    # https://github.com/<owner>/<repo>/releases/download/<tag>/<asset>
    parts = notat.DIAR_FILES[0]["url"].split("github.com/")[1].split("/", 5)
    owner, repo, tag, asset = parts[0], parts[1], parts[4], parts[5]
    published = None
    for a in get_json(f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}")["assets"]:
        if a["name"] == asset:
            published = (a.get("digest") or "").removeprefix("sha256:")
    assert published == notat.DIAR_FILES[0]["sha256"], f"{asset}: the pin is not the published digest"


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
