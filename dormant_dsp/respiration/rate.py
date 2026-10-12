"""Breaths-per-minute from a band-passed waveform: peak counting + FFT, cross-checked."""
import numpy as np
from scipy.signal import find_peaks

import config
from respiration.spectral import spectrum


def rate_from_peaks(x, fs, min_bpm=config.MIN_BPM, max_bpm=config.MAX_BPM):
    x = np.asarray(x, float)
    dist = max(int(fs * 60 / max_bpm * 0.8), 1)
    peaks, _ = find_peaks(x, distance=dist, prominence=0.5 * np.std(x))
    out = {"bpm": None, "peaks": peaks, "ibi_cv": None}
    if len(peaks) < 3:
        return out
    ibi = np.diff(peaks) / fs
    ibi = ibi[(ibi >= 60 / max_bpm) & (ibi <= 60 / min_bpm)]
    if len(ibi) < 2:
        return out
    out["bpm"] = float(60.0 / np.median(ibi))
    out["ibi_cv"] = float(ibi.std() / ibi.mean())
    return out


def rate_from_fft(x, fs, band=config.BREATH_BAND_HZ):
    f, P = spectrum(x, fs, pad=8)
    m = (f >= band[0]) & (f <= band[1])
    f0 = f[m][np.argmax(P[m])]
    near = m & (np.abs(f - f0) <= 0.04)
    return {"bpm": float(f0 * 60), "peak_ratio": float(P[near].sum() / (P[m].sum() + 1e-12)),
            "freqs": f, "power": P}


def estimate_rate(x, fs):
    """Run both methods. Final BPM = average if they agree (<=2 BPM), else the FFT value."""
    p, s = rate_from_peaks(x, fs), rate_from_fft(x, fs)
    if p["bpm"] is not None and abs(p["bpm"] - s["bpm"]) <= 2.0:
        bpm = 0.5 * (p["bpm"] + s["bpm"])
    else:
        bpm = s["bpm"]
    return {"bpm": bpm, "bpm_peaks": p["bpm"], "bpm_fft": s["bpm"], "peaks": p["peaks"],
            "ibi_cv": p["ibi_cv"], "peak_ratio": s["peak_ratio"],
            "freqs": s["freqs"], "power": s["power"]}
