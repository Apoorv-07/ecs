"""PCA across subcarriers: many noisy traces -> a few clean components."""
import numpy as np

import config
from respiration.spectral import band_power_ratio


def pca(X: np.ndarray, n_components: int = config.PCA_N):
    """X: (T, K) amplitude. Returns (scores (T,n), explained_variance_ratio (n,), components (n,K))."""
    Xc = X - X.mean(axis=0)
    sd = Xc.std(axis=0)
    sd[sd == 0] = 1.0                 # so loud subcarriers don't dominate
    Z = Xc / sd
    U, S, Vt = np.linalg.svd(Z, full_matrices=False)
    n = min(n_components, Z.shape[1])
    var = S ** 2
    return U[:, :n] * S[:n], var[:n] / var.sum(), Vt[:n]


def best_breathing_component(scores: np.ndarray, fs: float, band=config.BREATH_BAND_HZ):
    """Pick the component with the largest share of its power in the breathing band.

    (PC1 is usually slow drift / movement, which is why we don't just take PC1.)
    """
    ratios = np.array([band_power_ratio(scores[:, i], fs, band) for i in range(scores.shape[1])])
    return int(np.argmax(ratios)), ratios
