"""Replay a recording through LiveAnalyzer exactly as the backend would, save the feature table.

    python scripts/run_live.py data/raw/<file>.csv
    python scripts/run_live.py --synthetic 15
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

import config
from respiration.live import LiveAnalyzer, FEATURES


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?")
    ap.add_argument("--synthetic", type=float)
    ap.add_argument("--out", default="outputs/features.csv")
    a = ap.parse_args()
    if not a.csv and not a.synthetic:
        ap.error("give a CSV path or --synthetic BPM")

    if a.synthetic:
        from tests.synth import make_synthetic
        from preprocess.clean import usable_subcarriers
        t, X = make_synthetic(bpm=a.synthetic, dur=180, irregular=True)
        csi = np.zeros((len(t), config.N_SUBCARRIERS), complex); csi[:, usable_subcarriers()] = X
        rssi, seq = np.full(len(t), -50.0), np.arange(len(t))
    else:
        from ingest.parser import load_csv
        rec = load_csv(a.csv)
        t, rssi, csi, seq = rec.t, rec.rssi, rec.csi, rec.seq

    out = LiveAnalyzer().push_many(t, rssi, csi, seq)
    if not out:
        sys.exit(f"Need at least {config.WINDOW_S}s of data for the first result.")
    df = pd.DataFrame([o["features"] for o in out], columns=FEATURES)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    df.to_csv(a.out, index=False)
    print(df.round(2).to_string(index=False))
    print("Saved ->", a.out)


if __name__ == "__main__":
    main()
