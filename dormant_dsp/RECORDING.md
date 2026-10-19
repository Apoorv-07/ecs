# Dormant - CSI recording and dataset management (Member 3)

## 1. What the receiver sends today (Task A: written down from `Dormant_RX.c`)

| Item | Today |
|---|---|
| Link to the PC | USB serial, 115200 baud (default port in the scripts: COM10) |
| One record | one text line: `CSI_DATA,<rssi>,<v1>,...,<v128>` (130 comma-separated fields) |
| `v1..v128` | raw CSI bytes as signed ints (-128..127): 64 subcarriers x (imag, real) pairs. The firmware does NOT parse them. |
| Other lines | ESP boot/log messages (ignored, counted as `other_lines`) |
| Timestamp | **none** from the board; the PC stamps the arrival time (packets arrive in bursts, so this is coarse) |
| Packet number | **none** -> lost packets cannot be counted |
| Sender address | **none**; the receiver listens in promiscuous mode on channel 1 to all data/management frames, so other Wi-Fi devices are captured too (recording shows ~12.7 Hz against the 10 Hz transmitter) |
| Not available | phase as a separate field, channel/bandwidth, noise floor, packet length (to be confirmed with Member 2) |

To confirm with Member 2: is the number of values always exactly 128? (Anything else is rejected as malformed.)

### Proposed extended record (needs Member 2, and Member 1 for the packet number)
`CSI_DATA,<seq>,<esp_ts_us>,<mac>,<rssi>,<v1>,...,<v128>`  (133 fields)
* `seq` - packet counter inserted by the transmitter (Member 1) and read by the receiver
* `esp_ts_us` - `esp_timer_get_time()` at reception (microseconds, board clock)
* `mac` - sender address, `AA:BB:CC:DD:EE:FF`

The recorder already accepts this format automatically (and `--mac` keeps only our transmitter).
If Member 2 prefers a different order or format, only `parse_line()` in `ingest/recorder.py` changes.

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
