"""Replay a recording through MotionAnalyzer and save the short-window motion feature table.

    python scripts/run_motion.py data/raw/<file>.csv
    python scripts/run_motion.py --synthetic        (static room, with a movement burst)
    python scripts/run_motion.py data/raw/<file>.csv --win 3 --hop 1 --out outputs/motion.csv
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

import config
from respiration.motion import MotionAnalyzer, MOTION_FEATURES


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--win", type=float, default=3.0)
    ap.add_argument("--hop", type=float, default=1.0)
    ap.add_argument("--out", default="outputs/motion_features.csv")
    a = ap.parse_args()
    if not a.csv and not a.synthetic:
        ap.error("give a CSV path or --synthetic")

    if a.synthetic:
        from preprocess.clean import usable_subcarriers
        rng = np.random.default_rng(0)
        t = np.arange(0, 60, 0.1); K = len(usable_subcarriers())
        X = 10 + rng.uniform(-2, 2, K) + rng.normal(0, 0.05, (len(t), K))
        m = (t >= 30) & (t < 45)
        X[m] += 1.5 * np.sin(2 * np.pi * 0.7 * t[m, None] + rng.uniform(0, 6.28, K))
        csi = np.zeros((len(t), config.N_SUBCARRIERS), complex); csi[:, usable_subcarriers()] = X
        rssi, seq = np.full(len(t), -55.0), np.arange(len(t))
    else:
        from ingest.parser import load_csv
        rec = load_csv(a.csv)
        t, rssi, csi, seq = rec.t, rec.rssi, rec.csi, rec.seq

    out = MotionAnalyzer(win_s=a.win, hop_s=a.hop).push_many(t, rssi, csi, seq)
    if not out:
        sys.exit(f"Need at least {a.win}s of data.")
    df = pd.DataFrame([o["features"] for o in out], columns=MOTION_FEATURES)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    df.to_csv(a.out, index=False)
    print(df[["t_end", "motion_score", "std_mean", "mac_mean", "pc1_ratio",
              "valid_frac", "max_gap_s", "status"]].round(3).head(25).to_string(index=False))
    print(f"... {len(df)} rows. Status counts: {df['status'].value_counts().to_dict()}")
    print("Saved ->", a.out)


if __name__ == "__main__":
    main()
