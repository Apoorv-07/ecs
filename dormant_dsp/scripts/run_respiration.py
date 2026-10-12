"""Breathing rate from a recording (or from fake data to sanity-check the code):

    python scripts/run_respiration.py data/raw/<file>.csv
    python scripts/run_respiration.py --synthetic 15      # pretend someone breathes at 15 BPM
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config
from ingest.parser import load_csv
from preprocess.clean import preprocess
from respiration.pipeline import analyze


def get_pre(a):
    if a.synthetic:
        from tests.synth import make_synthetic
        from preprocess.clean import hampel, resample_uniform
        t, X = make_synthetic(bpm=a.synthetic, dur=120, irregular=True)
        Xc, _ = hampel(X)
        tu, Xu, valid = resample_uniform(t, Xc)
        return {"t": tu, "amp": Xu, "valid": valid}
    return preprocess(load_csv(a.csv))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?")
    ap.add_argument("--synthetic", type=float)
    ap.add_argument("--out", default="outputs/respiration.png")
    a = ap.parse_args()
    if not a.csv and not a.synthetic:
        ap.error("give a CSV path or --synthetic BPM")

    pre = get_pre(a)
    res = analyze(pre)
    if not res:
        sys.exit(f"Recording shorter than {config.WINDOW_S}s -- need a longer one.")

    print(f"{'window (s)':>14} {'BPM':>6} {'peaks':>6} {'fft':>6} {'quality':>8}  label")
    for r in res:
        i = r["rate_info"]
        pk = "-" if i["bpm_peaks"] is None else f"{i['bpm_peaks']:.1f}"
        print(f"{r['t_start']:6.0f}-{r['t_end']:<6.0f} {r['bpm']:6.1f} {pk:>6} {i['bpm_fft']:6.1f} "
              f"{r['quality']['score']:8.2f}  {r['quality']['label']}")

    r, fs = res[-1], config.TARGET_FS
    tw = np.arange(len(r["waveform"])) / fs
    fig, ax = plt.subplots(1, 2, figsize=(14, 4.5))
    ax[0].plot(tw, r["waveform"]); pk = r["rate_info"]["peaks"]
    ax[0].plot(tw[pk], r["waveform"][pk], "rv")
    ax[0].set(title=f"Breathing waveform (last window)  ->  {r['bpm']:.1f} BPM, quality {r['quality']['label']}",
              xlabel="time in window (s)")
    f, P = r["rate_info"]["freqs"], r["rate_info"]["power"]
    m = f <= 1.5
    ax[1].plot(f[m] * 60, P[m]); ax[1].axvspan(config.MIN_BPM, config.MAX_BPM, alpha=0.15)
    ax[1].set(title="Spectrum of waveform (shaded = breathing band)", xlabel="breaths / min")
    fig.tight_layout(); os.makedirs(os.path.dirname(a.out), exist_ok=True); fig.savefig(a.out, dpi=110)
    print("Saved ->", a.out)


if __name__ == "__main__":
    main()
