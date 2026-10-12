"""Replay a recording as if it were live, and cut it into sliding windows."""
import time
from typing import Iterator
import numpy as np

from ingest.parser import CSIRecording


def replay(rec: CSIRecording, speed: float = 1.0) -> Iterator[tuple[float, float, np.ndarray]]:
    """Yield (t, rssi, csi_row) with the original timing. speed=10 -> 10x faster, 0 -> no sleeping."""
    start = time.perf_counter()
    for i in range(len(rec)):
        if speed > 0:
            wait = rec.t[i] / speed - (time.perf_counter() - start)
            if wait > 0:
                time.sleep(wait)
        yield rec.t[i], rec.rssi[i], rec.csi[i]


def iter_windows(t: np.ndarray, X: np.ndarray, win_s: float, hop_s: float):
    """Yield (t_win, X_win) sliding windows. Use this for near-real-time processing."""
    start = t[0]
    while start + win_s <= t[-1] + 1e-9:
        m = (t >= start) & (t < start + win_s)
        yield t[m], X[m]
        start += hop_s
