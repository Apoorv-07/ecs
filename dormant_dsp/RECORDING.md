
# Dormant - CSI recording and dataset management (Member 3)

## 1. What the receiver sends (Task A, updated for the Arduino firmware of 2026-10-21)

| Item | Now |
|---|---|
| Link to the PC | USB serial, 115200 baud |
| One record | `CSI_DATA,<seq>,<esp_ts_us>,<mac>,<rssi>,<v1>,...,<v128>` (133 fields) - the "extended" format |
| `v1..v128` | signed bytes (-128..127), 64 complex pairs (imag, real); LLTF, 20 MHz, channel 1 |
| `seq` | **receiver-side counter** of packets that passed the filter. It detects loss inside the receiver (queue drops) but NOT packets lost in the air: the transmitter does not number its packets. Air loss shows up only as time gaps. |
| `esp_ts_us` | `esp_timer_get_time()` at reception (board clock, microseconds since boot) |
| `mac` | sender address; the receiver already drops every packet that is not from the transmitter (`68:09:47:5C:2B:F0`) |
| Dead data | first 4 bytes zeroed by the receiver when `first_word_invalid`; pairs 27-37 are always zero (null tones) |
| Other lines | `RX_STATS ...` every 5 s (callbacks, other_mac, queue_drops, ...) and boot messages: kept in `raw_serial.log`, counted as `other_lines` |
| Transmitter | fixed 6 Mbps OFDM, one frame every 100 ms + transmit time: measured 8.2-9.7 Hz, not exactly 10 Hz |
| Not available | phase as a separate field, noise floor, bandwidth/channel fields, TX packet number |

Still to confirm with Member 2: whether an `RX_STATS` summary should be saved into metadata.json
(queue drops are the only loss counter the board has).

## 2. One session = one folder

```
dataset/raw/session_001/
  raw_serial.log      every line exactly as received:  <PC epoch seconds> <TAB> <original line>
  csi_data.csv        parsed records (same columns as before + seq, esp_ts_us, mac when available)
  metadata.json       id, times, condition, participant code, receiver info, counts, interruptions,
                      quality report, raw-vs-csv check, file hashes, valid/invalid verdict
  recording_log.txt   warnings, errors, status messages
```
The recorder never overwrites a session, never invents labels (you give the condition),
and saves to disk as it goes (a crash loses at most a fraction of a second).

## 3. Procedure (Task D)

```powershell
# 1  Close idf.py monitor, power the transmitter, plug in the receiver
# 2  Is the receiver alive and sending good CSI?
python scripts\record_session.py --preflight --port COM10
# 3-8  New session ID, metadata, record, stop, close files (Ctrl+C or --duration)
python scripts\record_session.py --port COM10 --condition paced_breathing --participant P01 ^
    --reference-bpm 12 --duration 240 --rx-firmware "Dormant_RX 2026-10-08" ^
    --notes "lying on back, metronome 12/min, started 21:05"
# 9  Quality checks run automatically at the end; the verdict is printed and saved
# 10 Review it yourself if needed (saved as manual_review in metadata.json)
python scripts\check_session.py dataset\raw\session_001 --review valid --comment "ok"
# Overview for Member 5 (also writes dataset\sessions_index.csv)
python scripts\list_sessions.py
```
No hardware? `python scripts\record_session.py --simulate --condition test --duration 70`

### Verdict rules (`validity` in metadata.json)
* **invalid**: session ended abnormally (connection lost), no records, shorter than 60 s,
  more than 5% malformed records, packet rate below 5 Hz, NaN values, or the csv does not
  match the raw log.
* **valid_with_warnings**: weak signal (< -80 dBm), a gap over 3 s, rate more than 15% above
  the 10 Hz transmitter rate (other devices captured), an interruption that recovered, or
  skipped malformed records.
* **valid**: none of the above. The "info" notes (no packet numbers, no board timestamp, no
  sender address) are listed but do not change the verdict until the firmware provides them.

Robustness: unplugged cable -> retries for 60 s, then ends the session cleanly keeping all
data; no valid data for 10 s -> a "stall" warning and an interruption entry.

## 4. Tests
`python -m pytest tests/test_recorder.py` (12 tests: parsing, folders, malformed records,
short sessions, reconnect, unrecoverable disconnect, stalls, MAC filter, session numbering,
tamper detection, preflight). The `--simulate` option exercises the whole chain without boards.

## 5. Requests to other members
* **Member 2:** send the sender MAC, a board timestamp and a packet counter on every line (format
  above), confirm the 128-values assumption, and give me the firmware version string for the metadata.
* **Member 1:** put a running packet number inside the transmitted packet and keep the 10 Hz rate steady.
* **Member 5 / Member 4:** confirm the list of condition names and the metadata fields you need.
