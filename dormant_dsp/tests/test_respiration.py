import numpy as np
import pytest
from respiration.pipeline import analyze_window
from preprocess.clean import hampel, resample_uniform
from respiration.bandpass import StreamingBandpass, bandpass
from tests.synth import make_synthetic


@pytest.mark.parametrize("bpm", [8, 12, 15, 20, 26])
def test_clean_recovery(bpm):
    t, X = make_synthetic(bpm=bpm, dur=60)
    r = analyze_window(X, np.ones(len(t), bool))
    assert abs(r["bpm"] - bpm) < 1.5
    assert r["quality"]["label"] in ("good", "fair")


def test_irregular_packets_through_full_chain():
    t, X = make_synthetic(bpm=16, dur=120, irregular=True)
    Xc, _ = hampel(X)
    tu, Xu, valid = resample_uniform(t, Xc)
    n = 600
    r = analyze_window(Xu[:n], valid[:n])
    assert abs(r["bpm"] - 16) < 1.5


def test_pure_noise_gets_poor_quality():
    rng = np.random.default_rng(1)
    X = np.abs(10 + rng.normal(0, 1, (600, 54)))
    assert analyze_window(X, np.ones(600, bool))["quality"]["label"] != "good"


def test_streaming_matches_offline_causal():
    x = np.sin(2 * np.pi * 0.25 * np.arange(0, 60, 0.1))
    s = StreamingBandpass(10)
    y = np.concatenate([s.process(x[i:i + 7]) for i in range(0, len(x), 7)])
    assert np.allclose(y, bandpass(x, 10, causal=True) , atol=0.15)
