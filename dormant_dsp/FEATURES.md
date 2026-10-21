

## Interface contract v1 (confirmed 2026-10-21, for Member 5 to build against)

**CSI layout (current Arduino firmware, LLTF, 20 MHz, channel 1)**
* A record has 128 signed bytes = 64 complex pairs (imag, real). CSV columns `Subcarrier_1..128`;
  pair p (0-based) = columns `Subcarrier_{2p+1}`, `Subcarrier_{2p+2}`.
* **Dead pairs (always zero in S01-S07): 0, 1, 27-37 (13 pairs). Active pairs: 51 = 0-based 2-26 and 38-63.**
  Pairs 0-1 are zeroed by the receiver (`first_word_invalid`); 27-37 are null/guard tones.
  This is `NULL_SUBCARRIERS`/`DROP_SUBCARRIER_0` in `config.py`. The recorder compares every new session
  with this mask (`csi_layout` in metadata.json) and warns if the firmware/configuration drifts.
* Feature amplitudes are in raw byte units (not calibrated).

**Timestamps**
* `t_start`, `t_end` = seconds since the FIRST packet of the recording (receiver-PC clock).
  On S01-S07 the PC clock and the ESP timestamp agree (median spacing 0.100 s on both).
  Absolute time = first `Timestamp` in `csi_data.csv` + t (PC local time; session timezone is in metadata.json).
* Rows overlap (60 s window, 10 s hop): never put neighbouring rows of one session in different
  train/validation/test sets. Split by whole session (and later by participant).
* Mapping to 30 s sleep epochs (proposal): use the row whose `t_end` equals the epoch end, so the
  window covers that epoch plus the 30 s before it.

**Respiration rows** (`LiveAnalyzer`): window 60 s, hop 10 s, first row after 60 s.
* Band 0.1-0.5 Hz = **6-30 breaths/min**. `bpm` is NaN unless `status == "ok"`:
  quality label fair/good AND `peak_ratio >= 0.6` AND `valid_frac >= 0.5`.
* Quality fields: `quality_score` 0-1 (label: good >= 0.7, fair >= 0.4), `peak_ratio`, `valid_frac`, `status`.
* **The schema is frozen; the numbers are NOT validated.** Thresholds are provisional. No recording has an
  independent reference rate yet. On S01-S07, 1 of 168 windows is trusted, and the `peak_ratio`
  distribution of the lying/resting sessions is the same as for the empty room and for white noise
  (median 0.36-0.41, 95th percentile about 0.55). Do NOT use `bpm` as a label or as ground truth.
  Use `quality_score`, `peak_ratio` and `status` as features and expect `bpm` to be mostly NaN until
  a paced-breathing session (S08) shows that breathing is detectable.

**Motion rows** (`MotionAnalyzer`): window 3 s, hop 1 s (see below).
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
