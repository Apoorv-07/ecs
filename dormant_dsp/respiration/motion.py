"""Short-window motion features for Member 4 (occupancy / movement / events).

Same pattern as respiration.live.LiveAnalyzer, but with short windows:

    from respiration.motion import MotionAnalyzer
    ma = MotionAnalyzer()                      # 3 s window, 1 s hop
    for t, rssi, csi_row, seq in packets:
        out = ma.push(t, rssi, csi_row, seq)   # None, except once per HOP_S
        if out is not None:
            out["features"]        # flat dict, MOTION_FEATURES columns
            out["subcarrier_var"]  # (K,) per-subcarrier amplitude variance of this window
            out["subcarrier_idx"]  # (K,) original subcarrier index of each entry above
            out["pca_scores"]      # (N, 3) PCA scores of the window (valid samples only)

Design choices (read these before trusting a number):
* Works on RAW amplitude, i.e. BEFORE the Hampel filter. Hampel replaces sharp spikes with the
  local median, and a sudden body movement looks exactly like a spike.
* PCA here is z-scored inside the window, so it throws away absolute amplitude. It is provided
  for comparison (pc1_ratio, pca_scores); the raw statistics are the primary movement signals.
* Statistics use only samples that come from real packets (valid=True). Stretches where the
  nearest packets were more than MAX_GAP_S apart are interpolated lines, which would fake a
  "calm" signal, so they are excluded and reported through valid_frac / status.
* motion_score is NaN unless status == "ok" (same idea as bpm in the respiration features);
  motion_score_raw is always filled in for debugging.
* Thresholds that separate "empty" from "moving" must be tuned on labelled recordings.
"""
from collections import deque
import math

import numpy as np

import config
from preprocess.clean import usable_subcarriers, resample_uniform
from preprocess.pca import pca

MOTION_FEATURES = [
    "t_start", "t_end",            # s, packet clock
    "motion_score",                # unitless, NaN when status != ok  <- the one to threshold
    "motion_score_raw",            # same number, never gated (debugging)
    "std_mean",                    # mean over subcarriers of amplitude std (raw amplitude units)
    "mac_mean",                    # mean absolute change between consecutive samples (raw units)
    "var_mean", "var_max",         # per-subcarrier variance summary (raw units^2)
    "amp_mean",                    # mean amplitude level (changes when a person enters/leaves)
    "pc1_ratio",                   # share of variance in PCA component 1 (0..1)
    "rssi_mean", "rssi_std",       # dBm
    "valid_frac",                  # share of the window made of real (not interpolated) data
    "max_gap_s",                   # longest silence between real packets inside the window
    "n_packets", "packet_rate_hz",
    "packet_loss_pct",             # from seq numbers; NaN until Members 1/2 add them
    "status",                      # ok / low_coverage / too_few_packets
]

NAN = float("nan")


class MotionAnalyzer:
    def __init__(self, fs=config.TARGET_FS, win_s=3.0, hop_s=1.0,
                 min_valid_frac=0.8, min_packets=5, n_pca=3):
        self.fs, self.win_s, self.hop_s = fs, win_s, hop_s
        self.min_valid_frac, self.min_packets, self.n_pca = min_valid_frac, min_packets, n_pca
        self.idx = usable_subcarriers()
        self.keep_s = win_s + 2.0
        self.reset()

    # ---------------------------------------------------------------- state
    def reset(self):
        self.t, self.amp, self.rssi, self.seq = deque(), deque(), deque(), deque()
        self.next_emit = None
        self.dropped_old = 0

    # ---------------------------------------------------------------- input
    def push(self, t, rssi, csi_row, seq=None):
        """Feed ONE packet. csi_row: complex (64,) or the raw 128 ints from the ESP32."""
        t = float(t)
        if self.t and t < self.t[-1]:
            self.dropped_old += 1
            return None
        if self.t and t - self.t[-1] > self.keep_s:
            self.reset()

        row = np.asarray(csi_row)
        if not np.iscomplexobj(row):
            if row.size != 2 * config.N_SUBCARRIERS:
                return None
            a, b = row[0::2].astype(float), row[1::2].astype(float)
            row = (b + 1j * a) if config.IQ_ORDER == "imag_real" else (a + 1j * b)
        if row.size != config.N_SUBCARRIERS:
            return None
        amp = np.abs(row[self.idx])
        if not np.all(np.isfinite(amp)):
            return None

        self.t.append(t); self.amp.append(amp)
        self.rssi.append(float(rssi)); self.seq.append(None if seq is None else int(seq))
        while self.t and self.t[0] < t - self.keep_s:
            self.t.popleft(); self.amp.popleft(); self.rssi.popleft(); self.seq.popleft()

        if self.next_emit is None:
            self.next_emit = t + self.win_s
            return None
        if t >= self.next_emit:
            self.next_emit = max(self.next_emit + self.hop_s, t + self.hop_s * 0.5)
            return self._analyze()
        return None

    def push_many(self, ts, rssis, csi, seqs=None):
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
        rssi = np.asarray(self.rssi, float)
        seq = list(self.seq)
        if len(t) < 2:
            return None

        tu, Xu, valid = resample_uniform(t, X, self.fs)     # RAW amplitude: no Hampel here
        n = int(self.win_s * self.fs)
        if len(tu) < 2:
            return None
        tu, Xu, valid = tu[-n:], Xu[-n:], valid[-n:]      # last win_s seconds (or all we have)
        K = Xu.shape[1]

        t0, t1 = float(tu[0]), float(tu[-1])
        in_win = (t >= t0) & (t <= t1)
        tw = t[in_win]
        n_pkts = int(in_win.sum())
        max_gap = float(np.diff(tw).max()) if n_pkts >= 2 else self.win_s
        valid_frac = float(valid.sum()) / n          # relative to the FULL window: partial windows score low

        # ---- statistics on REAL samples only
        var = np.full(K, NAN)
        std_mean = mac_mean = amp_mean = motion_raw = NAN
        Xv = Xu[valid]
        if len(Xv) >= 5:
            std = Xv.std(axis=0)
            var = std ** 2
            mean = Xv.mean(axis=0)
            std_mean = float(std.mean())
            amp_mean = float(mean.mean())
            cv = std / np.where(mean > 0, mean, np.nan)
            motion_raw = float(np.nanmedian(cv))
            pair = valid[1:] & valid[:-1]
            d = np.abs(np.diff(Xu, axis=0))[pair]
            if len(d):
                mac_mean = float(d.mean())

        pc1_ratio, scores = NAN, np.empty((0, 0))
        if len(Xv) >= 10:
            scores, evr, _ = pca(Xv, self.n_pca)
            pc1_ratio = float(evr[0])

        # ---- packet-level link info
        loss = NAN
        s_in = [s for s, k in zip(seq, in_win) if k and s is not None]
        if len(s_in) > 1:
            dd = np.diff(np.asarray(s_in, np.int64))
            lost = int((dd[dd > 1] - 1).sum())
            loss = 100.0 * lost / (lost + len(s_in))
        r_in = rssi[in_win]

        if n_pkts < self.min_packets:
            status = "too_few_packets"
        elif valid_frac < self.min_valid_frac:
            status = "low_coverage"
        else:
            status = "ok"

        feats = {
            "t_start": t0, "t_end": t1,
            "motion_score": motion_raw if status == "ok" else NAN,
            "motion_score_raw": motion_raw,
            "std_mean": std_mean, "mac_mean": mac_mean,
            "var_mean": float(np.nanmean(var)) if np.any(np.isfinite(var)) else NAN,
            "var_max": float(np.nanmax(var)) if np.any(np.isfinite(var)) else NAN,
            "amp_mean": amp_mean, "pc1_ratio": pc1_ratio,
            "rssi_mean": float(r_in.mean()) if len(r_in) else NAN,
            "rssi_std": float(r_in.std()) if len(r_in) else NAN,
            "valid_frac": valid_frac, "max_gap_s": max_gap,
            "n_packets": n_pkts, "packet_rate_hz": n_pkts / self.win_s,
            "packet_loss_pct": loss, "status": status,
        }
        return {"features": feats, "subcarrier_var": var, "subcarrier_idx": self.idx,
                "pca_scores": scores, "pca_t": tu[valid][:len(scores)] if len(scores) else tu[:0]}
