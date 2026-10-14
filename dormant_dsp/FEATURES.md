# Respiration feature interface (Member 3 -> Members 4, 5, 6)

Produced by `respiration.live.LiveAnalyzer.push(...)`.
First row after `WINDOW_S` = 60 s of data, then one row every `HOP_S` = 10 s.
Time = packet clock in seconds (same clock as the packets you feed in).

| Column | Unit | Meaning |
|---|---|---|
| t_start, t_end | s | window bounds |
| bpm | breaths/min | trusted rate; **NaN** when status != ok. Use this one. |
| bpm_raw | breaths/min | estimator output even when untrusted (debugging only) |
| n_breaths | count | breath peaks found in the window |
| ibi_cv | ratio | breathing-interval variability (std/mean); NaN if < 3 breaths |
| breath_amplitude | a.u. | robust peak-to-trough of the breathing waveform. Relative: compare within one setup/session, not across rooms |
| quality_score | 0-1 | trust in this window |
| quality_label | good/fair/poor | thresholds 0.7 / 0.4 (first guesses, to be tuned) |
| peak_ratio | 0-1 | share of breathing-band power in the main spectral peak |
| valid_frac | 0-1 | share of window that is real data, not interpolated gaps |
| packet_rate_hz | Hz | packets received per second |
| packet_loss_pct | % | from seq numbers; NaN until TX/RX firmware sends them |
| status | enum | ok / low_quality / low_coverage |

Rules for consumers
* Never treat NaN `bpm` as 0. For ML (Member 5): impute or use `status` as a feature.
* A NaN `bpm` with a person present is itself information (movement/poor signal).
* Waveform for the dashboard comes separately: `result["waveform"]` (TARGET_FS Hz, one
  window, band-passed) with matching times in `result["t_waveform"]`.

---

# Motion features (Member 3 -> Member 4)

Produced by `respiration.motion.MotionAnalyzer.push(t, rssi, csi_row, seq)` (same call pattern as
`LiveAnalyzer`). Default: 3 s window, 1 s hop; change with `MotionAnalyzer(win_s=..., hop_s=...)`.
CSV for any recording: `python scripts/run_motion.py <file>.csv`.

| Column | Unit | Meaning |
|---|---|---|
| t_start, t_end | s | window bounds (packet clock) |
| motion_score | unitless | median over subcarriers of (std / mean amplitude). **NaN when status != ok.** Threshold this one. |
| motion_score_raw | unitless | same, never gated (debugging) |
| std_mean | amplitude units | mean over subcarriers of the amplitude std |
| mac_mean | amplitude units | mean absolute change between consecutive (10 Hz) samples |
| var_mean, var_max | amplitude units^2 | summary of the per-subcarrier variance |
| amp_mean | amplitude units | mean amplitude level (shifts when someone enters/leaves) |
| pc1_ratio | 0-1 | share of variance in PCA component 1 (z-scored inside the window) |
| rssi_mean, rssi_std | dBm | link strength in the window |
| valid_frac | 0-1 | share of the FULL window made of real packets; partial windows score low |
| max_gap_s | s | longest silence between real packets in the window |
| n_packets, packet_rate_hz | count, Hz | packets received in the window |
| packet_loss_pct | % | from seq numbers; NaN until firmware sends them |
| status | enum | ok / low_coverage (valid_frac < 0.8) / too_few_packets (< 5) |

Also in each result (not in the flat row): `subcarrier_var` (per-subcarrier variance vector),
`subcarrier_idx` (original subcarrier index of each entry), `pca_scores` (top 3 PCA scores of the
window, real samples only) and `pca_t` (their times).

Notes for Member 4
* Features use RAW amplitude (before the Hampel filter), so sharp movement is not smoothed away.
* Statistics use only samples that come from real packets, never interpolated stretches.
* After a packet outage you get explicit `too_few_packets` / `low_coverage` rows with NaN
  `motion_score`; do not read them as "calm". If no rows arrive at all for more than a few
  seconds the link is down (an outage longer than ~5 s makes the analyzer reset and stay quiet
  until it has refilled).
* The score is relative to the setup: a weak link (RSSI around -88 dBm, as in the first recording)
  has a high noise floor, so thresholds must come from empty-room (session A) recordings made
  with the same setup, not from numbers in this file.
