"""Load a CSI CSV into a standard in-memory format and validate it.

Supports:
  * the CURRENT logger format:  Timestamp, RSSI, Subcarrier_1..Subcarrier_128
  * the FUTURE format (once Members 1/2 add them): optional columns
        seq, esp_ts_us  -> used automatically if present
"""
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

import config


@dataclass
class CSIRecording:
    t: np.ndarray                 # host time in seconds since first packet, shape (N,)
    rssi: np.ndarray              # shape (N,)
    csi: np.ndarray               # complex, shape (N, 64)
    seq: np.ndarray | None = None       # packet IDs, if available
    esp_ts_us: np.ndarray | None = None  # ESP32 hardware timestamp, if available
    source: str = ""
    meta: dict = field(default_factory=dict)

    def __len__(self):
        return len(self.t)


def _raw_to_complex(raw: np.ndarray) -> np.ndarray:
    first, second = raw[:, 0::2], raw[:, 1::2]
    if config.IQ_ORDER == "imag_real":
        return second + 1j * first
    return first + 1j * second


def load_csv(path: str) -> CSIRecording:
    df = pd.read_csv(path)
    ts = pd.to_datetime(df["Timestamp"])
    t = (ts - ts.iloc[0]).dt.total_seconds().to_numpy()

    sc_cols = [c for c in df.columns if c.startswith("Subcarrier_")]
    if len(sc_cols) != 2 * config.N_SUBCARRIERS:
        raise ValueError(f"Expected {2*config.N_SUBCARRIERS} subcarrier columns, got {len(sc_cols)}")
    raw = df[sc_cols].to_numpy(dtype=float)

    return CSIRecording(
        t=t,
        rssi=df["RSSI"].to_numpy(dtype=float),
        csi=_raw_to_complex(raw),
        seq=df["seq"].to_numpy() if "seq" in df else None,
        esp_ts_us=df["esp_ts_us"].to_numpy() if "esp_ts_us" in df else None,
        source=str(path),
    )


def validate(rec: CSIRecording) -> dict:
    """Return a dict of quality numbers. Print it, log it, or show it on the dashboard."""
    n = len(rec)
    dur = float(rec.t[-1] - rec.t[0]) if n > 1 else 0.0
    dt = np.diff(rec.t)
    amp = np.abs(rec.csi)
    report = {
        "packets": n,
        "duration_s": round(dur, 2),
        "mean_rate_hz": round(n / dur, 2) if dur > 0 else None,
        "median_dt_ms": round(float(np.median(dt)) * 1000, 1) if n > 1 else None,
        "max_gap_s": round(float(dt.max()), 2) if n > 1 else None,
        f"gaps_over_{config.GAP_WARN_S}s": int((dt > config.GAP_WARN_S).sum()),
        "non_monotonic_time": int((dt < 0).sum()),
        "duplicate_timestamps": int((dt == 0).sum()),
        "rssi_mean": round(float(rec.rssi.mean()), 1),
        "rssi_min": float(rec.rssi.min()),
        "rssi_max": float(rec.rssi.max()),
        "nan_values": int(np.isnan(amp).sum()),
        "always_zero_subcarriers": np.where((amp == 0).all(axis=0))[0].tolist(),
    }
    if rec.seq is not None:
        s = np.diff(rec.seq.astype(np.int64))
        report["lost_packets_from_seq"] = int((s[s > 1] - 1).sum())
    else:
        report["warning"] = "No seq column: packet loss cannot be measured. Ask Members 1/2."
    if report["mean_rate_hz"] and report["mean_rate_hz"] > config.TARGET_FS * 1.1:
        report["warning_rate"] = ("Rate is above the TX rate -> RX may be capturing packets "
                                  "from other devices (no MAC filter).")
    return report
