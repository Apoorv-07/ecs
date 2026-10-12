"""Butterworth band-pass for the breathing band."""
import numpy as np
from scipy.signal import butter, sosfilt, sosfiltfilt, sosfilt_zi

import config


def design(fs, low=config.BREATH_BAND_HZ[0], high=config.BREATH_BAND_HZ[1], order=config.BP_ORDER):
    return butter(order, [low, high], btype="bandpass", fs=fs, output="sos")


def bandpass(x, fs, causal=False, **kw):
    """causal=False: zero-phase (no lag) -- use for recordings / windows.
    causal=True : ordinary filter (adds lag) -- use only if you must filter sample by sample."""
    sos = design(fs, **kw)
    x = np.asarray(x, float)
    return sosfilt(sos, x) if causal else sosfiltfilt(sos, x)


class StreamingBandpass:
    """Keeps filter state between chunks, for live data:  y = filt.process(new_samples)."""

    def __init__(self, fs, **kw):
        self.sos = design(fs, **kw)
        self.zi = None

    def process(self, chunk):
        chunk = np.asarray(chunk, float)
        if self.zi is None:
            self.zi = sosfilt_zi(self.sos) * chunk[0]
        y, self.zi = sosfilt(self.sos, chunk, zi=self.zi)
        return y
