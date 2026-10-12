"""Raw CSI -> clean, uniformly sampled amplitude matrix."""
import numpy as np
from scipy.ndimage import median_filter

import config


def usable_subcarriers() -> np.ndarray:
    idx = np.arange(config.N_SUBCARRIERS)
    bad = set(config.NULL_SUBCARRIERS)
    if config.DROP_SUBCARRIER_0:
        bad.add(0)
    return np.array([i for i in idx if i not in bad])


def to_amplitude(csi: np.ndarray, idx: np.ndarray | None = None) -> np.ndarray:
    """(N,64) complex -> (N,K) amplitude using only usable subcarriers."""
    idx = usable_subcarriers() if idx is None else idx
    return np.abs(csi[:, idx])


def resample_uniform(t: np.ndarray, X: np.ndarray, fs: float = config.TARGET_FS,
                     max_gap_s: float = config.MAX_GAP_S):
    """Linear-interpolate onto a uniform grid.

    Returns (t_u, X_u, valid). valid[i] is False where the nearest real packets were
    more than max_gap_s apart (the data there is made up -- do not trust it).
    """
    t_u = np.arange(t[0], t[-1], 1.0 / fs)
    X_u = np.column_stack([np.interp(t_u, t, X[:, j]) for j in range(X.shape[1])])
    right = np.searchsorted(t, t_u, side="left").clip(1, len(t) - 1)
    gap = t[right] - t[right - 1]
    return t_u, X_u, gap <= max_gap_s


def hampel(X: np.ndarray, window: int = config.HAMPEL_WINDOW,
           n_sigmas: float = config.HAMPEL_SIGMAS):
    """Hampel outlier filter on each column. Returns (X_clean, outlier_mask)."""
    X = np.asarray(X, dtype=float)
    one_d = X.ndim == 1
    if one_d:
        X = X[:, None]
    med = median_filter(X, size=(window, 1), mode="nearest")
    mad = median_filter(np.abs(X - med), size=(window, 1), mode="nearest")
    out = np.abs(X - med) > n_sigmas * 1.4826 * mad
    Xc = np.where(out, med, X)
    return (Xc[:, 0], out[:, 0]) if one_d else (Xc, out)


def preprocess(rec):
    """One call: recording -> dict with everything the next stages need.

    Order matters: Hampel runs on the REAL packets first (before resampling),
    because interpolated samples are straight lines and would confuse the filter.
    """
    amp_pkt = to_amplitude(rec.csi)
    amp_pkt_clean, outliers = hampel(amp_pkt)
    t_u, amp_u, valid = resample_uniform(rec.t, amp_pkt_clean)
    return {"t": t_u, "amp": amp_u, "valid": valid,
            "t_pkt": rec.t, "amp_pkt": amp_pkt, "outliers": outliers,
            "subcarriers": usable_subcarriers()}
