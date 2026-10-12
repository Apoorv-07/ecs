"""Small spectrum helpers shared by PCA selection, rate estimation and quality."""
import numpy as np


def spectrum(x, fs, pad=8):
    """Hann-windowed, zero-padded power spectrum. Returns (freqs_hz, power)."""
    x = np.asarray(x, float)
    x = x - x.mean()
    n = len(x) * pad
    P = np.abs(np.fft.rfft(x * np.hanning(len(x)), n=n)) ** 2
    return np.fft.rfftfreq(n, 1.0 / fs), P


def band_power_ratio(x, fs, band):
    """Fraction of (non-DC) power that lies inside `band`."""
    f, P = spectrum(x, fs, pad=1)
    keep = f > 0
    inb = (f >= band[0]) & (f <= band[1])
    return float(P[inb].sum() / (P[keep].sum() + 1e-12))
