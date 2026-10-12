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
