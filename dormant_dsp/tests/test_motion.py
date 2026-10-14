import math
import numpy as np

import config
from preprocess.clean import usable_subcarriers
from respiration.motion import MotionAnalyzer, MOTION_FEATURES


def _csi(X):
    c = np.zeros((len(X), config.N_SUBCARRIERS), complex)
    c[:, usable_subcarriers()] = X
    return c


def _stream(dur=60, seed=0, noise=0.05, move=None, spike_at=None, drop=None):
    """Static room (amplitude ~10 + small noise), packets every 0.1 s with jitter.
    move=(t0, t1): big body-movement-like fluctuation added in that interval.
    spike_at=t: one packet with a single-subcarrier jump. drop=(t0,t1): packets missing."""
    rng = np.random.default_rng(seed)
    t = np.arange(0, dur, 0.1) + rng.uniform(-0.01, 0.01, int(dur / 0.1))
    K = len(usable_subcarriers())
    X = 10 + rng.uniform(-2, 2, K) + rng.normal(0, noise, (len(t), K))
    if move:
        m = (t >= move[0]) & (t < move[1])
        ph = rng.uniform(0, 2 * np.pi, K)
        X[m] += 1.5 * np.sin(2 * np.pi * 0.7 * t[m, None] + ph) + rng.normal(0, 0.3, (m.sum(), K))
    if spike_at is not None:
        i = int(np.argmin(np.abs(t - spike_at))); X[i, 5] += 8.0
    if drop:
        keep = ~((t >= drop[0]) & (t < drop[1])); t, X = t[keep], X[keep]
    return t, X


def _run(t, X, seq=None):
    return MotionAnalyzer().push_many(t, np.full(len(t), -55.0), _csi(X), seq)


def test_columns_and_timing():
    out = _run(*_stream(dur=40))
    assert set(out[0]["features"]) == set(MOTION_FEATURES)
    ts = [o["features"]["t_end"] for o in out]
    assert abs(ts[0] - 3.0) < 0.6
    assert np.allclose(np.diff(ts), 1.0, atol=0.3)


def test_moving_scores_far_higher_than_empty():
    out = _run(*_stream(dur=60, move=(30, 45)))
    still = [o["features"]["motion_score"] for o in out if o["features"]["t_end"] < 28]
    moving = [o["features"]["motion_score"] for o in out if 34 < o["features"]["t_end"] < 44]
    assert still and moving
    assert np.nanmean(moving) > 5 * np.nanmean(still)


def test_sharp_spike_is_not_filtered_away():
    base = _run(*_stream(dur=30, seed=1))
    spk = _run(*_stream(dur=30, seed=1, spike_at=15.0))
    vb = max(o["features"]["var_max"] for o in base)
    vs = max(o["features"]["var_max"] for o in spk)
    assert vs > 10 * vb                       # raw amplitude: Hampel would have erased this


def test_per_subcarrier_variance_vector_and_pca():
    out = _run(*_stream(dur=20, move=(5, 20)))
    r = out[-1]
    assert r["subcarrier_var"].shape == r["subcarrier_idx"].shape == (len(usable_subcarriers()),)
    assert r["pca_scores"].shape[1] == 3
    assert 0 < r["features"]["pc1_ratio"] <= 1


def test_gap_gives_nan_score_and_flag():
    out = _run(*_stream(dur=40, drop=(20, 24)))
    bad = [o["features"] for o in out if 23.9 < o["features"]["t_end"] < 26.0]
    assert bad and all(f["status"] != "ok" and math.isnan(f["motion_score"]) for f in bad)
    assert any(f["max_gap_s"] >= 2.99 for f in bad) and len(bad) >= 3
    good = [o["features"] for o in out if o["features"]["t_end"] < 18]
    assert all(f["status"] == "ok" for f in good)


def test_packet_loss_from_seq():
    t, X = _stream(dur=20)
    seq = np.arange(len(t)); keep = np.ones(len(t), bool); keep[::10] = False
    out = _run(t[keep], X[keep], seq[keep])
    assert 7 < out[-1]["features"]["packet_loss_pct"] < 13


def test_bad_packets_ignored():
    ma = MotionAnalyzer()
    assert ma.push(0.0, -50, np.zeros(100)) is None
    assert ma.push(0.1, -50, np.full(128, np.nan)) is None
    ma.push(0.2, -50, np.ones(128)); ma.push(0.1, -50, np.ones(128))
    assert len(ma.t) == 1 and ma.dropped_old == 1
