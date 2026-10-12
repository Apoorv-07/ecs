# dormant_dsp  (Member 3: CSI pipeline + signal processing)

Place this folder inside your project, next to csi_logger.py:

    ECS_2/
      csi_logger.py
      Dormant_TX/  Dormant_RX/
      dormant_dsp/        <-- this folder

## Setup (Windows, from inside dormant_dsp)
    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt

## Run
1. Copy your CSV (e.g. Dormant_CSI_Stable_*.csv) into data\raw\
2. python scripts\inspect_csv.py data\raw\<file>.csv
   -> prints a quality report and saves outputs\overview.png
3. python -m pytest

## Where things go
config.py              all tunable settings
ingest/parser.py       load_csv(), validate()
ingest/replay.py       replay(), iter_windows()
preprocess/clean.py    amplitude, Hampel, resample_uniform, preprocess()
viz/plots.py           diagnostic plots
scripts/inspect_csv.py first thing to run on any recording
tests/                 pytest tests

## Breathing stage (added)
preprocess/pca.py          pca(), best_breathing_component()
respiration/spectral.py    spectrum(), band_power_ratio()
respiration/bandpass.py    bandpass(), StreamingBandpass
respiration/rate.py        estimate_rate()  (peaks + FFT, cross-checked)
respiration/quality.py     signal_quality()  -> score 0..1 + label
respiration/pipeline.py    analyze_window()  <- Member 6 calls this, analyze()
scripts/run_respiration.py run on a CSV, or --synthetic 15 to sanity-check
tests/synth.py             fake CSI with a known breathing rate

    python scripts\run_respiration.py --synthetic 15
    python scripts\run_respiration.py data\raw\<file>.csv

Needs >= 60 s of data per window (config.WINDOW_S).
