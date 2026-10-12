import math
import numpy as np
import pytest

import config
from preprocess.clean import usable_subcarriers
from respiration.live import LiveAnalyzer, FEATURES
from tests.synth import make_synthetic


def _csi(X):
    c = np.zeros((len(X), config.N_SUBCARRIERS), complex)
    c[:, usable_subcarriers()] = X
    return c


@pytest.mark.parametrize("bpm", [10, 16, 24])
def test_live_recovers_rate(bpm):
    t, X = make_synthetic(bpm=bpm, dur=130, irregular=True)
    out = LiveAnalyzer().push_many(t, np.full(len(t), -50.0), _csi(X), np.arange(len(t)))
    assert len(out) >= 5
    for r in out:
        f = r["features"]
        assert f["status"] == "ok" and abs(f["bpm"] - bpm) < 1.5
        assert set(FEATURES) == set(f)


def test_first_result_after_one_window_then_every_hop():
    t, X = make_synthetic(bpm=15, dur=130, fs=10.0)
    la, times = LiveAnalyzer(), []
    for i in range(len(t)):
        if la.push(t[i], -50, _csi(X[i:i + 1])[0]) is not None:
            times.append(t[i])
    assert abs(times[0] - config.WINDOW_S) < 1.0
    assert np.allclose(np.diff(times), config.HOP_S, atol=0.5)


def test_noise_gives_nan_bpm_not_a_number():
    rng = np.random.default_rng(3)
    t = np.arange(0, 90, 0.1)
    X = np.abs(10 + rng.normal(0, 1, (len(t), 54)))
    out = LiveAnalyzer().push_many(t, np.zeros(len(t)), _csi(X))
    assert out and all(math.isnan(r["features"]["bpm"]) for r in out)


def test_packet_loss_from_seq():
    t, X = make_synthetic(bpm=15, dur=75, fs=10.0)
    seq = np.arange(len(t)); keep = np.ones(len(t), bool); keep[::10] = False   # drop 10 %
    out = LiveAnalyzer().push_many(t[keep], np.zeros(keep.sum()), _csi(X)[keep], seq[keep])
    assert 8 < out[0]["features"]["packet_loss_pct"] < 12


def test_raw_128_int_packets_and_bad_packets_are_handled():
    la = LiveAnalyzer()
    assert la.push(0.0, -50, np.zeros(100)) is None            # wrong length -> ignored
    assert la.push(0.1, -50, np.full(128, np.nan)) is None      # NaN -> ignored
    assert la.push(0.2, -50, np.ones(128)) is None              # valid raw packet accepted
    assert len(la.t) == 1
    la.push(0.1, -50, np.ones(128))                             # time went backwards -> ignored
    assert la.dropped_old == 1


def test_long_outage_resets_buffer():
    la = LiveAnalyzer()
    la.push(0.0, 0, np.ones(128)); la.push(1.0, 0, np.ones(128))
    la.push(500.0, 0, np.ones(128))
    assert len(la.t) == 1
