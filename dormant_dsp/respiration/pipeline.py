"""Preprocessed amplitude -> breathing waveform, rate and quality, window by window."""
import numpy as np

import config
from preprocess.pca import pca, best_breathing_component
from respiration.bandpass import bandpass
from respiration.rate import estimate_rate
from respiration.quality import signal_quality


def analyze_window(X, valid, fs=config.TARGET_FS):
    """X: (T,K) cleaned amplitude for ONE window. Returns a dict (this is what Member 6 calls)."""
    scores, evr, _ = pca(X)
    k, ratios = best_breathing_component(scores, fs)
    wave = bandpass(scores[:, k], fs)
    info = estimate_rate(wave, fs)
    q = signal_quality(info, float(np.mean(valid)))
    return {"bpm": info["bpm"], "quality": q, "waveform": wave, "component": k,
            "band_ratios": ratios, "explained_var": evr, "rate_info": info}


def analyze(pre, fs=config.TARGET_FS, win_s=config.WINDOW_S, hop_s=config.HOP_S):
    """Slide a window over a whole preprocessed recording."""
    n_win, hop = int(win_s * fs), int(hop_s * fs)
    results = []
    for s in range(0, len(pre["t"]) - n_win + 1, hop):
        sl = slice(s, s + n_win)
        r = analyze_window(pre["amp"][sl], pre["valid"][sl], fs)
        r["t_start"], r["t_end"] = float(pre["t"][s]), float(pre["t"][s + n_win - 1])
        results.append(r)
    return results
