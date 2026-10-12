"""Fake CSI with a known breathing rate, to test the pipeline without hardware."""
import numpy as np


def make_synthetic(bpm=15.0, dur=120.0, fs=10.0, n_sc=54, noise=1.0, seed=0, irregular=False):
    rng = np.random.default_rng(seed)
    if irregular:   # like the real logger: bursts, jitter and a few long gaps
        t = np.cumsum(rng.choice([0.03, 0.03, 0.1, 0.1, 0.4], size=int(dur * 12)))
        t = t[t < dur]
        t = t[~(((t > 40) & (t < 42.5)) | ((t > 90) & (t < 91.5)))]
    else:
        t = np.arange(0, dur, 1 / fs)
    f = bpm / 60.0
    gain = rng.uniform(0.3, 1.5, n_sc) * rng.choice([-1, 1], n_sc)
    phase = rng.uniform(0, 0.8, n_sc)
    base = rng.uniform(8, 14, n_sc)
    drift = np.sin(2 * np.pi * 0.015 * t + 1.0)[:, None] * rng.uniform(1, 4, n_sc)
    other = 0.5 * np.sin(2 * np.pi * 0.9 * t)[:, None] * rng.uniform(0, 1, n_sc)
    X = (base + gain * np.sin(2 * np.pi * f * t[:, None] + phase) + drift + other
         + rng.normal(0, noise, (len(t), n_sc)))
    return t, np.abs(X)
