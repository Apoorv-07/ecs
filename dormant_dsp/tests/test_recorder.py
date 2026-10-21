
import json
import os
import tempfile

from ingest.recorder import (SessionRecorder, SimSource, SourceError, EndOfSource, parse_line,
                             verify_session, preflight, N_VALUES)
from ingest.parser import load_csv


class FakeClock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def _rec(tmp, source, clk, **kw):
    return SessionRecorder(source, tmp, condition=kw.pop("condition", "test"), clock=clk,
                           sleep=clk.advance, echo=False, **kw)


def _good_line(rssi=-50):
    return "CSI_DATA," + str(rssi) + "," + ",".join(["5"] * N_VALUES)


# ------------------------------------------------------------------ parsing
def test_parse_line_variants():
    r, why = parse_line(_good_line())
    assert why is None and r["seq"] is None and len(r["values"]) == N_VALUES
    ext = "CSI_DATA,7,123456,24:6f:28:ae:11:22,-40," + ",".join(["1"] * N_VALUES)
    r, why = parse_line(ext)
    assert why is None and r["seq"] == 7 and r["mac"] == "24:6F:28:AE:11:22"
    assert parse_line("I (123) DORMANT_RX: RX Sniffer Mode Active")[1] == "other_line"
    assert parse_line("CSI_DATA,-50,1,2,3")[1] == "wrong_field_count_5"
    assert parse_line(_good_line().replace(",5,5", ",x,5", 1))[1] == "non_numeric_field"
    assert parse_line(_good_line(rssi=30))[1] == "rssi_out_of_range"
    assert parse_line(_good_line().replace(",5,", ",500,", 1))[1] == "value_out_of_range"
    assert parse_line(",".join(["5"] * 60))[1] == "garbled_line"


# ------------------------------------------------------------------ recording
def test_good_session_files_metadata_and_roundtrip():
    clk = FakeClock()
    with tempfile.TemporaryDirectory() as tmp:
        m = _rec(tmp, SimSource(10, 1000, False, clk.advance), clk, participant="P01",
                 reference_bpm=15).run()
        d = os.path.join(tmp, "session_001")
        assert sorted(os.listdir(d)) == ["csi_data.csv", "metadata.json",
                                         "raw_serial.log", "recording_log.txt"]
        assert m["status"] == "completed" and m["counts"]["records_saved"] == 1000
        assert m["validity"] == "valid", m["validity_reasons"] + m["warnings"]
        assert m["raw_vs_csv"]["match"] and m["experiment"]["participant_code"] == "P01"
        assert len(m["files"]["csi_data.csv"]["sha256"]) == 64
        assert json.load(open(os.path.join(d, "metadata.json")))["session_id"] == "session_001"
        rec = load_csv(os.path.join(d, "csi_data.csv"))     # the existing loader reads it
        assert len(rec) == 1000 and abs(rec.t[-1] - 99.9) < 0.05


def test_malformed_records_are_logged_and_can_invalidate():
    clk = FakeClock()
    with tempfile.TemporaryDirectory() as tmp:
        m = _rec(tmp, SimSource(10, 1000, False, clk.advance, bad_every=10), clk).run()
        assert m["counts"]["malformed"] == 100 and m["counts"]["records_saved"] == 900
        assert m["validity"] == "invalid" and any("malformed" in r for r in m["validity_reasons"])
        log = open(os.path.join(tmp, "session_001", "recording_log.txt")).read()
        assert log.count("Malformed record") == 100
        raw = open(os.path.join(tmp, "session_001", "raw_serial.log")).read()
        assert raw.count("\n") == 1000                       # bad lines kept in the raw log too


def test_short_session_is_invalid():
    clk = FakeClock()
    with tempfile.TemporaryDirectory() as tmp:
        m = _rec(tmp, SimSource(10, 300, False, clk.advance), clk).run()
        assert m["validity"] == "invalid" and any("too short" in r for r in m["validity_reasons"])


def test_duration_stops_recording():
    clk = FakeClock()
    with tempfile.TemporaryDirectory() as tmp:
        m = _rec(tmp, SimSource(10, None, False, clk.advance), clk, duration_s=70).run()
        assert m["stop_reason"] == "duration reached"
        assert 69 <= m["duration_s"] <= 71 and 690 <= m["counts"]["records_saved"] <= 710


class FlakySource:
    """Wraps a source: raises SourceError once at line `at`; reopen() works after `fail_reopens`."""
    def __init__(self, inner, at, fail_reopens=0):
        self.inner, self.at, self.fail, self.n, self.down = inner, at, fail_reopens, 0, False

    def open(self): self.inner.open()
    def close(self): self.inner.close()

    def reopen(self):
        if self.fail > 0:
            self.fail -= 1
            raise SourceError("port busy")
        self.down = False

    def read_line(self):
        if self.down:
            raise SourceError("device disconnected")
        self.n += 1
        if self.n == self.at:
            self.down = True
            raise SourceError("device disconnected")
        return self.inner.read_line()


def test_reconnect_after_disconnect_keeps_data():
    clk = FakeClock()
    with tempfile.TemporaryDirectory() as tmp:
        src = FlakySource(SimSource(10, 1000, False, clk.advance), at=300, fail_reopens=1)
        m = _rec(tmp, src, clk, retry_s=2.0).run()
        assert m["status"] == "completed" and m["counts"]["records_saved"] == 1000
        assert len(m["interruptions"]) == 1 and m["interruptions"][0]["recovered"]
        assert m["validity"] == "valid_with_warnings"


def test_unrecoverable_disconnect_ends_cleanly_with_metadata():
    clk = FakeClock()
    with tempfile.TemporaryDirectory() as tmp:
        src = FlakySource(SimSource(10, 1000, False, clk.advance), at=300, fail_reopens=10 ** 6)
        m = _rec(tmp, src, clk, reconnect_s=10, retry_s=2).run()
        assert m["status"] == "interrupted" and m["counts"]["records_saved"] == 299
        assert m["validity"] == "invalid" and not m["interruptions"][0]["recovered"]
        assert m["raw_vs_csv"]["match"]


class GapSource:
    """After `after` lines, returns None (= timeout, nothing received) `n_none` times."""
    def __init__(self, inner, after, n_none, clk):
        self.inner, self.after, self.n_none, self.clk, self.k = inner, after, n_none, clk, 0

    def open(self): pass
    def close(self): pass
    def reopen(self): pass

    def read_line(self):
        self.k += 1
        if self.after < self.k <= self.after + self.n_none:
            self.clk.advance(1.0)
            return None
        return self.inner.read_line()


def test_stall_is_detected_and_reported():
    clk = FakeClock()
    with tempfile.TemporaryDirectory() as tmp:
        src = GapSource(SimSource(10, 800, False, clk.advance), after=100, n_none=20, clk=clk)
        m = _rec(tmp, src, clk, stall_s=10).run()
        assert [i["type"] for i in m["interruptions"]] == ["stall"]
        assert m["interruptions"][0]["recovered"] and m["quality"]["max_gap_s"] > 15
        assert any("max" not in w and "gap" in w for w in m["warnings"])


def test_mac_filter_and_extended_columns():
    clk = FakeClock()
    macs = ("24:6F:28:AE:11:22", "AA:BB:CC:DD:EE:FF")
    with tempfile.TemporaryDirectory() as tmp:
        m = _rec(tmp, SimSource(10, 1000, False, clk.advance, extended=True, macs=macs), clk,
                 mac_filter="24:6f:28:ae:11:22").run()
        assert m["counts"]["records_saved"] == 500 and m["counts"]["filtered_other_mac"] == 500
        assert m["receiver"]["record_format"] == "extended" and m["raw_vs_csv"]["match"]
        rec = load_csv(os.path.join(tmp, "session_001", "csi_data.csv"))
        assert rec.seq is not None and len(rec.seq) == 500 and rec.esp_ts_us is not None


def test_session_ids_increment_and_never_overwrite():
    clk = FakeClock()
    with tempfile.TemporaryDirectory() as tmp:
        for _ in range(2):
            _rec(tmp, SimSource(10, 50, False, clk.advance), clk).run()
        assert sorted(os.listdir(tmp)) == ["session_001", "session_002"]
        try:
            _rec(tmp, SimSource(10, 5, False, clk.advance), clk, session_id="session_001").run()
            assert False, "should refuse to overwrite"
        except FileExistsError:
            pass


def test_tampered_csv_is_detected():
    clk = FakeClock()
    with tempfile.TemporaryDirectory() as tmp:
        _rec(tmp, SimSource(10, 200, False, clk.advance), clk).run()
        d = os.path.join(tmp, "session_001")
        assert verify_session(d)["match"]
        p = os.path.join(d, "csi_data.csv")
        lines = open(p).read().split("\n")
        parts = lines[5].split(","); parts[10] = "99"; lines[5] = ",".join(parts)
        open(p, "w").write("\n".join(lines))
        v = verify_session(d)
        assert not v["match"] and v["mismatched_rows"] == 1


def test_preflight():
    clk = FakeClock()
    r = preflight(SimSource(10, 100, False, clk.advance), seconds=5, clock=clk)
    assert r["ok"] and 8 <= r["rate_hz"] <= 11 and r["format"] == "basic"


def test_csi_layout_matches_mask_and_flags_drift():
    clk = FakeClock()
    with tempfile.TemporaryDirectory() as tmp:
        m = _rec(tmp, SimSource(10, 1000, False, clk.advance), clk).run()
        lay = m["csi_layout"]
        assert lay["mask_matches_config"] and lay["active_pairs_observed"] == 51
        assert m["validity"] == "valid"
        # firmware change: another pair goes dead -> flagged
        m2 = _rec(tmp, SimSource(10, 1000, False, clk.advance, dead_pairs={0, 1, 5, *range(27, 38)}),
                  clk).run()
        assert m2["csi_layout"]["dead_pairs_still_used"] == [5]
        assert m2["validity"] == "valid_with_warnings"
        assert any("CSI layout differs" in w for w in m2["warnings"])
