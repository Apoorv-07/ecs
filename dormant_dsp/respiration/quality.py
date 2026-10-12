"""Signal-quality score (0..1) so downstream modules know when to trust the rate.

The weights/thresholds are first guesses -- tune them on real labelled recordings.
"""
import numpy as np


def _lin(v, lo, hi):
    return float(np.clip((v - lo) / (hi - lo), 0.0, 1.0))


def signal_quality(info: dict, valid_frac: float) -> dict:
    spectral = _lin(info["peak_ratio"], 0.2, 0.7)                 # one clear spectral peak?
    regular = 0.0 if info["ibi_cv"] is None else 1 - _lin(info["ibi_cv"], 0.05, 0.3)
    coverage = _lin(valid_frac, 0.5, 0.9)                          # not made of interpolated gaps?
    if info["bpm_peaks"] is None:
        agree = 0.0
    else:
        d = abs(info["bpm_peaks"] - info["bpm_fft"])
        agree = 1.0 if d <= 1.5 else 0.5 if d <= 3 else 0.0       # two methods agree?
    score = 0.4 * spectral + 0.2 * regular + 0.2 * coverage + 0.2 * agree
    label = "good" if score >= 0.7 else "fair" if score >= 0.4 else "poor"
    return {"score": round(score, 3), "label": label, "spectral": round(spectral, 2),
            "regular": round(regular, 2), "coverage": round(coverage, 2), "agree": agree}
