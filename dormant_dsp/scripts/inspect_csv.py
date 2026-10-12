"""Run this first on any recording:

    python scripts/inspect_csv.py data/raw/<your_file>.csv
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingest.parser import load_csv, validate
from preprocess.clean import preprocess
from viz.plots import overview


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", default="outputs/overview.png")
    a = ap.parse_args()

    rec = load_csv(a.csv)
    print(json.dumps(validate(rec), indent=2))

    pre = preprocess(rec)
    print(f"\nResampled: {len(pre['t'])} samples @ 10 Hz, "
          f"{pre['amp'].shape[1]} subcarriers, "
          f"{(~pre['valid']).sum()} samples inside big gaps, "
          f"{pre['outliers'].sum()} outliers fixed by Hampel")

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    overview(rec, pre, a.out)
    print("Saved plot ->", a.out)


if __name__ == "__main__":
    main()
