"""Live / chunked respiration analysis  (this is what Member 6 calls).

    from respiration.live import LiveAnalyzer
    la = LiveAnalyzer()
    for t, rssi, csi_row, seq in packets:          # from the serial reader, or ingest.replay.replay()
        out = la.push(t, rssi, csi_row, seq)       # returns None most of the time
        if out is not None:                        # ...and one result every HOP_S seconds
            send_to_backend(out["features"], out["waveform"])

Time comes from the packets themselves (`t`, seconds, any monotonic clock), NOT from the
wall clock, so a replay at full speed behaves exactly like live.

The first result appears after WINDOW_S seconds of data, then one every HOP_S seconds.

`features` is a flat, JSON-safe dict (see FEATURES below) -> Members 4/5/6.
`waveform` is the band-passed breathing waveform of that window (numpy array, TARGET_FS Hz)
-> Member 6's live plot.
"""
from collections import deque
import math

import numpy as np

import config
from preprocess.clean import usable_subcarriers, hampel, resample_uniform
from respiration.pipeline import analyze_window

# Column order of `features` (use this for CSV headers / DataFrames).
FEATURES = [
    "t_start", "t_end",            # s, packet clock
    "bpm",                         # breaths/min, NaN when not trustworthy
    "bpm_raw",                     # what the estimator said, even when it is not trusted
    "n_breaths",                   # peaks found in the window
    "ibi_cv",                      # breathing-interval variability (std/mean), NaN if < 3 breaths
    "breath_amplitude",            # a.u., relative (see _amplitude)
    "quality_score",               # 0..1
    "quality_label",               # good / fair / poor
    "peak_ratio",                  # share of breathing-band power in the main peak, 0..1
    "valid_frac",                  # share of the window made of real (not interpolated) data
    "packet_rate_hz",              # packets actually received per second
    "packet_loss_pct",             # from seq numbers; NaN until Members 1/2 add them
    "status",                      # ok / low_quality / low_coverage
]


def _amplitude(wave):
    """Robust peak-to-trough size of the breathing waveform, per sqrt(sample).

    Arbitrary units: comparable between windows of the SAME setup (same config, same
    subcarriers), not between different rooms/hardware. Normalised by sqrt(N) because the
    PCA scores grow with window length."""
    wave = np.asarray(wave, float)
    return float((np.percentile(wave, 95) - np.percentile(wave, 5)) / math.sqrt(len(wave)))


class LiveAnalyzer:
    def __init__(self, fs=config.TARGET_FS, win_s=config.WINDOW_S, hop_s=config.HOP_S,
                 min_coverage=0.5, trust_labels=("good", "fair")):
        self.fs, self.win_s, self.hop_s = fs, win_s, hop_s
        self.min_coverage = min_coverage          # below this valid_frac -> bpm not trusted
        self.trust_labels = trust_labels          # quality labels whose bpm is passed on
        self.idx = usable_subcarriers()
        self.keep_s = win_s + 2.0                 # buffer length (a little more than a window)
        self.reset()

    # ---------------------------------------------------------------- state
    def reset(self):
        self.t = deque()          # packet times
        self.amp = deque()        # (K,) amplitudes of usable subcarriers
        self.seq = deque()        # packet ids (or None)
        self.next_emit = None     # packet-time at which the next result is due
        self.dropped_old = 0      # packets ignored because their time went backwards

    # ---------------------------------------------------------------- input
    def push(self, t, rssi, csi_row, seq=None):
        """Feed ONE packet. Returns a result dict when a new window is due, else None.

        csi_row: complex (64,)  -- or the raw 128 ints from the ESP32 (converted for you).
        """
        t = float(t)
        if self.t and t < self.t[-1]:
            self.dropped_old += 1                 # clock went backwards -> ignore this packet
            return None
        if self.t and t - self.t[-1] > self.win_s:
            self.reset()                          # long outage: old data is useless

        row = np.asarray(csi_row)
        if not np.iscomplexobj(row):
            if row.size != 2 * config.N_SUBCARRIERS:
                return None                       # corrupted packet: wrong length
            a, b = row[0::2].astype(float), row[1::2].astype(float)
            row = (b + 1j * a) if config.IQ_ORDER == "imag_real" else (a + 1j * b)
        if row.size != config.N_SUBCARRIERS:
            return None
        amp = np.abs(row[self.idx])
        if not np.all(np.isfinite(amp)):
            return None

        self.t.append(t)
        self.amp.append(amp)
        self.seq.append(None if seq is None else int(seq))
        while self.t and self.t[0] < t - self.keep_s:
            self.t.popleft(); self.amp.popleft(); self.seq.popleft()

        if self.next_emit is None:
            self.next_emit = t + self.win_s       # first window needs a full win_s of data
            return None
        if t >= self.next_emit:
            self.next_emit = max(self.next_emit + self.hop_s, t + self.hop_s * 0.5)
            return self._analyze()
        return None

    def push_many(self, ts, rssis, csi, seqs=None):
        """Feed a chunk of packets (arrays/lists). Returns the list of results produced."""
        out = []
        for i in range(len(ts)):
            r = self.push(ts[i], rssis[i] if rssis is not None else 0.0, csi[i],
                          None if seqs is None else seqs[i])
            if r is not None:
                out.append(r)
        return out

    # ---------------------------------------------------------------- analysis
    def _analyze(self):
        t = np.asarray(self.t, float)
        X = np.asarray(self.amp, float)
        t_end = float(t[-1])
        sel = t >= t_end - self.win_s - 1.0       # a little margin so resampling covers the start
        t, X = t[sel], X[sel]
        seq = [s for s, k in zip(self.seq, sel) if k]

        Xc, _ = hampel(X)                         # outliers on REAL packets, before resampling
        tu, Xu, valid = resample_uniform(t, Xc, self.fs)
        n = int(self.win_s * self.fs)
        if len(tu) < int(0.95 * n):
            return None                           # not enough data yet
        Xu, valid, tu = Xu[-n:], valid[-n:], tu[-n:]

        r = analyze_window(Xu, valid, self.fs)
        info, q = r["rate_info"], r["quality"]
        valid_frac = float(np.mean(valid))

        bpm_raw = float(r["bpm"])
        if valid_frac < self.min_coverage:
            status = "low_coverage"
        elif q["label"] not in self.trust_labels:
            status = "low_quality"
        else:
            status = "ok"
        bpm = bpm_raw if status == "ok" else float("nan")

        t0 = float(tu[0])
        in_win = (t >= t0)
        n_pkts = int(in_win.sum())
        loss = float("nan")
        s_in = [s for s, k in zip(seq, in_win) if k and s is not None]
        if len(s_in) > 1:
            d = np.diff(np.asarray(s_in, np.int64))
            lost = int((d[d > 1] - 1).sum())
            loss = 100.0 * lost / (lost + len(s_in))

        feats = {
            "t_start": t0, "t_end": float(tu[-1]),
            "bpm": bpm, "bpm_raw": bpm_raw,
            "n_breaths": int(len(info["peaks"])),
            "ibi_cv": float("nan") if info["ibi_cv"] is None else float(info["ibi_cv"]),
            "breath_amplitude": _amplitude(r["waveform"]),
            "quality_score": float(q["score"]), "quality_label": q["label"],
            "peak_ratio": float(info["peak_ratio"]),
            "valid_frac": valid_frac,
            "packet_rate_hz": n_pkts / self.win_s,
            "packet_loss_pct": loss,
            "status": status,
        }
        return {"features": feats, "waveform": r["waveform"], "t_waveform": tu,
                "peaks": info["peaks"], "quality_detail": q}
