
"""Controlled CSI recording: one folder per session, with metadata, a log and a quality verdict.

    dataset/raw/session_001/
        raw_serial.log      EXACTLY what the receiver sent: "<PC epoch seconds>\\t<original line>"
        csi_data.csv        parsed records (loadable with ingest.parser.load_csv)
        metadata.json       who/what/when, counts, interruptions, quality report, valid/invalid verdict
        recording_log.txt   warnings, errors and status messages

What the receiver sends today (Dormant_RX.c):
    CSI_DATA,<rssi>,<v1>,...,<v128>                       130 fields   <- "basic" format
It has NO board timestamp, NO packet number and NO sender address. A richer format is accepted
as soon as Member 2 provides it (this is a PROPOSAL; tell me if theirs differs):
    CSI_DATA,<seq>,<esp_ts_us>,<mac>,<rssi>,<v1>,...,<v128>   133 fields   <- "extended" format
Anything else that starts with CSI_DATA is logged as malformed and NOT saved to the csv
(it is still kept in raw_serial.log).
"""
import csv
import hashlib
import json
import math
import os
import re
import time
from datetime import datetime

N_VALUES = 128               # 64 subcarriers x (imag, real) int8 pairs
TX_RATE_HZ = 10.0            # what the transmitter firmware sends
MIN_DURATION_S = 60.0        # shorter than one respiration window -> not usable for tuning
MIN_RATE_HZ = 5.0
MAX_MALFORMED_FRAC = 0.05
MAX_GAP_WARN_S = 3.0
WEAK_RSSI_DBM = -80.0
MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$")
RECORDER_VERSION = "1.0"


class SourceError(Exception):
    """The data source failed (cable pulled, port busy...). The recorder will try to reconnect."""


class EndOfSource(Exception):
    """A finite source (simulation / replay) has no more lines."""


# ---------------------------------------------------------------------------- parsing
def parse_line(line):
    """Return (record, None) or (None, reason).

    reason == "other_line" means: not a CSI line (boot messages, ESP log lines). Not an error.
    Every other reason means a CSI-looking line was damaged -> malformed."""
    s = line.strip()
    if not s.startswith("CSI_DATA"):
        return (None, "other_line") if s.count(",") < 20 else (None, "garbled_line")
    parts = s.split(",")
    n = len(parts)
    try:
        if n == 2 + N_VALUES:
            seq = ts = mac = None
            rssi, vals = int(parts[1]), parts[2:]
        elif n == 5 + N_VALUES:
            seq, ts, mac = int(parts[1]), int(parts[2]), parts[3].strip()
            rssi, vals = int(parts[4]), parts[5:]
            if seq < 0 or ts < 0:
                return None, "negative_seq_or_timestamp"
            if not MAC_RE.match(mac):
                return None, "bad_mac"
        else:
            return None, f"wrong_field_count_{n}"
        values = [int(v) for v in vals]
    except ValueError:
        return None, "non_numeric_field"
    if not -127 <= rssi <= 0:
        return None, "rssi_out_of_range"
    if min(values) < -128 or max(values) > 127:
        return None, "value_out_of_range"
    return {"rssi": rssi, "values": values, "seq": seq, "esp_ts_us": ts,
            "mac": None if mac is None else mac.upper()}, None


# ---------------------------------------------------------------------------- sources
class SerialSource:
    """Reads lines from the ESP32 receiver over USB serial (needs `pip install pyserial`)."""

    def __init__(self, port, baud=115200, timeout=0.5):
        self.port, self.baud, self.timeout = port, baud, timeout
        self.ser = None
        self._buf = b""

    def open(self):
        try:
            import serial
        except ImportError:
            raise SourceError("pyserial is not installed: run  pip install pyserial")
        self._serial = serial
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=self.timeout)
        except (serial.SerialException, OSError) as e:
            raise SourceError(f"cannot open {self.port}: {e}")
        self._buf = b""

    def read_line(self):
        try:
            raw = self.ser.readline()
        except (self._serial.SerialException, OSError, AttributeError) as e:
            raise SourceError(str(e))
        if not raw:
            return None                         # timeout, nothing arrived
        if not raw.endswith(b"\n"):             # partial line: keep it for the next read
            self._buf += raw
            return None
        raw, self._buf = self._buf + raw, b""
        return raw.decode("utf-8", errors="replace")

    def reopen(self):
        self.close()
        self.open()

    def close(self):
        try:
            if self.ser is not None and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass


class SimSource:
    """Fake receiver for testing the whole chain without hardware (--simulate)."""

    def __init__(self, rate_hz=10.0, n_lines=None, realtime=True, tick=None, bad_every=0,
                 bpm=15.0, extended=False, macs=("24:6F:28:AE:11:22",), seed=0, dead_pairs=None):
        import random
        self.rate, self.n, self.realtime, self.tick = rate_hz, n_lines, realtime, tick
        self.bad_every, self.bpm, self.extended, self.macs = bad_every, bpm, extended, macs
        self.i = 0
        self.rng = random.Random(seed)
        self.base = [self.rng.randint(-40, 40) for _ in range(N_VALUES)]
        if dead_pairs is None:                   # behave like the real receiver: dead pairs are zero
            from preprocess.clean import usable_subcarriers
            dead_pairs = set(range(N_VALUES // 2)) - set(int(i) for i in usable_subcarriers())
        self.dead = {b for p in dead_pairs for b in (2 * p, 2 * p + 1)}

    def open(self):
        pass

    def reopen(self):
        pass

    def close(self):
        pass

    def read_line(self):
        if self.n is not None and self.i >= self.n:
            raise EndOfSource()
        dt = 1.0 / self.rate
        if self.realtime:
            time.sleep(dt)
        elif self.tick:
            self.tick(dt)
        self.i += 1
        if self.bad_every and self.i % self.bad_every == 0:
            return "CSI_DATA,-50,1,2,3\n"
        t = self.i * dt
        wave = 6.0 * math.sin(2 * math.pi * (self.bpm / 60.0) * t)
        vals = [0 if k in self.dead else
                max(-128, min(127, int(round(b + wave + self.rng.gauss(0, 1.5)))))
                for k, b in enumerate(self.base)]
        rssi = -50
        if self.extended:
            mac = self.macs[self.i % len(self.macs)]
            head = f"CSI_DATA,{self.i},{self.i * int(1e6 / self.rate)},{mac},{rssi}"
        else:
            head = f"CSI_DATA,{rssi}"
        return head + "," + ",".join(map(str, vals)) + "\n"


# ---------------------------------------------------------------------------- helpers
def _json_safe(o):
    if isinstance(o, dict):
        return {str(k): _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_safe(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if hasattr(o, "item"):
        return _json_safe(o.item())
    return o


def _write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_json_safe(obj), f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)                      # never leaves a half-written metadata.json


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _iso(epoch):
    return datetime.fromtimestamp(epoch).astimezone().isoformat(timespec="seconds")


def next_session_id(out_root):
    os.makedirs(out_root, exist_ok=True)
    nums = [int(m.group(1)) for d in os.listdir(out_root)
            if (m := re.fullmatch(r"session_(\d+)", d))]
    return f"session_{(max(nums) + 1 if nums else 1):03d}"


class SessionLog:
    def __init__(self, path, clock, echo=True):
        self.f = open(path, "a", encoding="utf-8")
        self.clock, self.echo = clock, echo
        self.counts = {"INFO": 0, "WARNING": 0, "ERROR": 0}
        self.warnings = []

    def _w(self, level, msg):
        stamp = datetime.fromtimestamp(self.clock()).isoformat(timespec="milliseconds")
        self.f.write(f"[{stamp}] {level}: {msg}\n")
        self.f.flush()
        self.counts[level] += 1
        if level != "INFO" and len(self.warnings) < 200:
            self.warnings.append(f"{level}: {msg}")
        if self.echo and level != "INFO":
            print(f"{level}: {msg}")

    def info(self, m): self._w("INFO", m)
    def warning(self, m): self._w("WARNING", m)
    def error(self, m): self._w("ERROR", m)
    def close(self): self.f.close()


# ---------------------------------------------------------------------------- verification
def verify_session(session_dir, mac_filter=None):
    """Re-parse raw_serial.log and check that csi_data.csv holds exactly the same records."""
    raw_path = os.path.join(session_dir, "raw_serial.log")
    csv_path = os.path.join(session_dir, "csi_data.csv")
    expected = []
    with open(raw_path, encoding="utf-8", errors="replace") as f:
        for ln in f:
            _, _, line = ln.rstrip("\n").partition("\t")
            rec, _ = parse_line(line)
            if rec is None:
                continue
            if mac_filter and rec["mac"] is not None and rec["mac"] != mac_filter.upper():
                continue
            expected.append((rec["rssi"], rec["values"]))
    saved = []
    if os.path.exists(csv_path):
        with open(csv_path, newline="", encoding="utf-8") as f:
            rd = csv.reader(f)
            next(rd, None)
            for row in rd:
                saved.append((int(row[1]), [int(v) for v in row[2:2 + N_VALUES]]))
    mism = sum(1 for a, b in zip(expected, saved) if a != b)
    return {"match": len(expected) == len(saved) and mism == 0,
            "raw_valid_records": len(expected), "csv_rows": len(saved), "mismatched_rows": mism}


def preflight(source, seconds=5.0, clock=time.time):
    """Listen for a few seconds WITHOUT saving: is the receiver alive and sending good CSI?"""
    source.open()
    t0, valid, bad, other, rssis, fmt = clock(), 0, 0, 0, [], None
    try:
        while clock() - t0 < seconds:
            try:
                line = source.read_line()
            except EndOfSource:
                break
            if line is None:
                continue
            rec, reason = parse_line(line)
            if rec:
                valid += 1
                rssis.append(rec["rssi"])
                fmt = "extended" if rec["seq"] is not None else "basic"
            elif reason == "other_line":
                other += 1
            else:
                bad += 1
    finally:
        source.close()
    el = max(clock() - t0, 1e-9)
    return {"ok": valid > 0 and bad <= 0.2 * (valid + bad), "valid_records": valid,
            "malformed": bad, "other_lines": other, "rate_hz": round(valid / el, 1),
            "rssi_mean": round(sum(rssis) / len(rssis), 1) if rssis else None, "format": fmt}


# ---------------------------------------------------------------------------- recorder
class SessionRecorder:
    def __init__(self, source, out_root, condition, participant=None, notes=None,
                 reference_bpm=None, rx_firmware=None, tx_firmware=None, setup_notes=None,
                 port=None, baud=None, mac_filter=None, session_id=None, duration_s=None,
                 reconnect_s=60.0, retry_s=2.0, stall_s=10.0, clock=time.time,
                 sleep=time.sleep, echo=True, status_every_s=5.0):
        self.source, self.out_root = source, out_root
        self.exp = {"condition": condition, "participant_code": participant,
                    "reference_bpm": reference_bpm, "notes": notes, "setup_notes": setup_notes}
        self.rx = {"port": port, "baud": baud, "firmware_rx": rx_firmware,
                   "firmware_tx": tx_firmware}
        self.mac_filter = mac_filter.upper() if mac_filter else None
        self.session_id = session_id or next_session_id(out_root)
        self.duration_s, self.reconnect_s, self.retry_s = duration_s, reconnect_s, retry_s
        self.stall_s, self.clock, self.sleep, self.echo = stall_s, clock, sleep, echo
        self.status_every_s = status_every_s
        self.dir = os.path.join(out_root, self.session_id)

    # ------------------------------------------------------------------ main loop
    def run(self):
        os.makedirs(self.dir, exist_ok=False)          # never overwrite an existing session
        self.log = SessionLog(os.path.join(self.dir, "recording_log.txt"), self.clock, self.echo)
        self.raw = open(os.path.join(self.dir, "raw_serial.log"), "w", encoding="utf-8")
        self.csv_f = self.csv_w = None
        self.fmt = None
        self.t0 = self.clock()
        self.lines = self.saved = self.malformed = self.other = self.filtered = 0
        self.reasons = {}
        self.interruptions = []
        self.last_valid_t, self.in_stall, self.stall_start = self.t0, False, None
        self._last_status, self._last_sync = self.t0, self.t0
        status, stop_reason = "completed", "input ended"

        self.log.info(f"Session {self.session_id} started. Condition: {self.exp['condition']}")
        self._write_meta({"status": "recording"})
        try:
            try:
                self.source.open()
            except SourceError as e:
                self.log.error(f"Could not open the data source: {e}")
                status, stop_reason = "aborted", f"could not open source: {e}"
                return self._finalize(status, stop_reason)
            while True:
                now = self.clock()
                if self.duration_s and now - self.t0 >= self.duration_s:
                    stop_reason = "duration reached"
                    break
                try:
                    line = self.source.read_line()
                except EndOfSource:
                    stop_reason = "input ended"
                    break
                except SourceError as e:
                    if self._reconnect(e):
                        continue
                    status, stop_reason = "interrupted", "connection lost and not recovered"
                    break
                self._check_stall(self.clock())
                if line is not None:
                    self._handle_line(line)
                self._periodic()
        except KeyboardInterrupt:
            stop_reason = "stopped by user"
            self.log.info("Stopped by user (Ctrl+C).")
        except Exception as e:                          # never lose the data already saved
            status, stop_reason = "aborted", f"unexpected error: {e!r}"
            self.log.error(f"Unexpected error: {e!r}")
        return self._finalize(status, stop_reason)

    # ------------------------------------------------------------------ per line
    def _handle_line(self, line):
        t = self.clock()
        self.lines += 1
        self.raw.write(f"{t:.6f}\t{line.rstrip(chr(10)).rstrip(chr(13))}\n")
        self.raw.flush()
        rec, reason = parse_line(line)
        if rec is None:
            if reason == "other_line":
                self.other += 1
            else:
                self.malformed += 1
                self.reasons[reason] = self.reasons.get(reason, 0) + 1
                if self.malformed <= 100:
                    self.log.warning(f"Malformed record #{self.malformed} ({reason}) at input "
                                     f"line {self.lines}: {line.strip()[:80]!r}")
                elif self.malformed == 101:
                    self.log.warning("More than 100 malformed records: not logging each one "
                                     "any more (counts are in metadata.json).")
            return
        fmt = "extended" if rec["seq"] is not None else "basic"
        if self.fmt is None:
            self.fmt = fmt
            self.log.info(f"Record format detected: {fmt}")
            if self.mac_filter and fmt == "basic":
                self.log.warning("A MAC filter was requested but the receiver does not send "
                                 "the sender address: ALL packets are being saved.")
        elif fmt != self.fmt:
            self.malformed += 1
            self.reasons["format_changed"] = self.reasons.get("format_changed", 0) + 1
            self.log.warning(f"Record format changed from {self.fmt} to {fmt}: record skipped")
            return
        if self.mac_filter and rec["mac"] is not None and rec["mac"] != self.mac_filter:
            self.filtered += 1
            self._valid_seen(t)
            return
        self._write_row(t, rec)
        self.saved += 1
        self._valid_seen(t)

    def _write_row(self, t, rec):
        if self.csv_w is None:
            self.csv_f = open(os.path.join(self.dir, "csi_data.csv"), "w", newline="",
                              encoding="utf-8")
            self.csv_w = csv.writer(self.csv_f)
            head = ["Timestamp", "RSSI"] + [f"Subcarrier_{i}" for i in range(1, N_VALUES + 1)]
            if self.fmt == "extended":
                head += ["seq", "esp_ts_us", "mac"]
            self.csv_w.writerow(head)
        row = [datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S.%f"), rec["rssi"]]
        row += rec["values"]
        if self.fmt == "extended":
            row += [rec["seq"], rec["esp_ts_us"], rec["mac"]]
        self.csv_w.writerow(row)
        self.csv_f.flush()

    def _valid_seen(self, t):
        if self.in_stall:
            dur = t - self.stall_start
            self.interruptions.append({"type": "stall", "start": _iso(self.stall_start),
                                       "end": _iso(t), "duration_s": round(dur, 1),
                                       "recovered": True})
            self.log.info(f"CSI data resumed after {dur:.1f} s without valid records.")
            self.in_stall = False
        self.last_valid_t = t

    # ------------------------------------------------------------------ robustness
    def _check_stall(self, now):
        if self.stall_s and not self.in_stall and now - self.last_valid_t >= self.stall_s:
            self.in_stall, self.stall_start = True, self.last_valid_t
            self.log.warning(f"No valid CSI records for {self.stall_s:.0f} s. Is the receiver "
                             "running and the transmitter on?")

    def _reconnect(self, err):
        t_lost = self.clock()
        self.log.warning(f"Connection lost: {err}. Trying to reconnect for "
                         f"{self.reconnect_s:.0f} s...")
        while self.clock() - t_lost < self.reconnect_s:
            self.sleep(self.retry_s)
            try:
                self.source.reopen()
            except SourceError:
                continue
            t_back = self.clock()
            self.interruptions.append({"type": "disconnect", "start": _iso(t_lost),
                                       "end": _iso(t_back),
                                       "duration_s": round(t_back - t_lost, 1),
                                       "recovered": True})
            self.log.info(f"Reconnected after {t_back - t_lost:.1f} s.")
            self.last_valid_t = t_back
            return True
        self.interruptions.append({"type": "disconnect", "start": _iso(t_lost),
                                   "end": None, "duration_s": None, "recovered": False})
        self.log.error("Could not reconnect. Ending the session; data saved so far is kept.")
        return False

    def _periodic(self):
        now = self.clock()
        if now - self._last_sync >= 5.0:                      # push data to the disk
            for f in (self.raw, self.csv_f):
                if f is not None:
                    f.flush()
                    os.fsync(f.fileno())
            self._last_sync = now
        if self.echo and now - self._last_status >= self.status_every_s:
            el = now - self.t0
            print(f"[{el:6.0f}s] saved {self.saved} | malformed {self.malformed} | "
                  f"{self.saved / max(el, 1e-9):.1f} rec/s")
            self._last_status = now

    # ------------------------------------------------------------------ end of session
    def _finalize(self, status, stop_reason):
        t_end = self.clock()
        if self.in_stall:
            self.interruptions.append({"type": "stall", "start": _iso(self.stall_start),
                                       "end": None, "duration_s": None, "recovered": False})
        for f in (self.raw, self.csv_f):
            if f is not None:
                f.flush()
                os.fsync(f.fileno())
                f.close()
        try:
            self.source.close()
        except Exception:
            pass
        duration = t_end - self.t0
        self.log.info(f"Session ended ({status}: {stop_reason}). Saved {self.saved} records, "
                      f"{self.malformed} malformed, in {duration:.1f} s.")

        csv_path = os.path.join(self.dir, "csi_data.csv")
        quality = layout = None
        if os.path.exists(csv_path) and self.saved >= 2:
            try:
                from ingest.parser import load_csv, validate
                rec_in = load_csv(csv_path)
                quality = validate(rec_in)
                layout = self._csi_layout(rec_in)
            except Exception as e:
                quality = {"error": f"quality check failed: {e!r}"}
                self.log.error(quality["error"])
        verify = verify_session(self.dir, self.mac_filter)
        if not verify["match"]:
            self.log.error(f"csi_data.csv does NOT match raw_serial.log: {verify}")

        validity, reasons, warns, info = self._evaluate(status, duration, quality, verify, layout)
        self.log.info(f"Verdict: {validity}" + (f" ({'; '.join(reasons)})" if reasons else ""))
        self.log.close()                                       # so its hash below is final

        files = {}
        for name in ("raw_serial.log", "csi_data.csv", "recording_log.txt"):
            p = os.path.join(self.dir, name)
            if os.path.exists(p):
                files[name] = {"bytes": os.path.getsize(p), "sha256": _sha256(p)}
        fields = ["timestamp_host", "rssi", f"csi_{N_VALUES}_values"]
        if self.fmt == "extended":
            fields += ["seq", "esp_ts_us", "mac"]
        meta = {
            "session_id": self.session_id, "status": status, "stop_reason": stop_reason,
            "start_time": _iso(self.t0), "end_time": _iso(t_end),
            "start_epoch_s": self.t0, "end_epoch_s": t_end, "duration_s": round(duration, 2),
            "experiment": self.exp,
            "receiver": {**self.rx, "record_format": self.fmt, "fields_available": fields,
                         "mac_filter": self.mac_filter},
            "counts": {"lines_received": self.lines, "records_saved": self.saved,
                       "malformed": self.malformed, "malformed_reasons": self.reasons,
                       "other_lines": self.other, "filtered_other_mac": self.filtered},
            "interruptions": self.interruptions, "quality": quality, "csi_layout": layout,
            "raw_vs_csv": verify,
            "validity": validity, "validity_reasons": reasons, "warnings": warns,
            "info": info, "manual_review": None,
            "log_warning_count": self.log.counts["WARNING"],
            "log_error_count": self.log.counts["ERROR"],
            "files": files, "recorder_version": RECORDER_VERSION,
        }
        self._write_meta(meta)
        return meta

    def _evaluate(self, status, duration, q, verify, layout=None):
        bad, warn, info = [], [], []
        csi_like = self.saved + self.malformed + self.filtered
        if status != "completed":
            bad.append(f"session ended abnormally ({status})")
        if self.saved == 0:
            bad.append("no records saved")
        if duration < MIN_DURATION_S:
            bad.append(f"too short ({duration:.0f} s, need at least {MIN_DURATION_S:.0f} s)")
        if csi_like and self.malformed / csi_like > MAX_MALFORMED_FRAC:
            bad.append(f"{100 * self.malformed / csi_like:.1f}% of records malformed "
                       f"(limit {100 * MAX_MALFORMED_FRAC:.0f}%)")
        if not verify["match"]:
            bad.append("csi_data.csv does not match raw_serial.log")
        if q and "error" not in q:
            rate = q.get("mean_rate_hz")
            if rate is not None and rate < MIN_RATE_HZ:
                bad.append(f"packet rate too low ({rate} Hz, need at least {MIN_RATE_HZ} Hz)")
            if rate is not None and rate > 1.15 * TX_RATE_HZ and self.fmt == "basic":
                warn.append(f"rate {rate} Hz is above the {TX_RATE_HZ:.0f} Hz transmitter rate: "
                            "the receiver is probably also capturing other devices")
            if (q.get("max_gap_s") or 0) > MAX_GAP_WARN_S:
                warn.append(f"longest gap between packets is {q['max_gap_s']} s")
            if (q.get("rssi_mean") or -999) < WEAK_RSSI_DBM:
                warn.append(f"weak signal (mean RSSI {q['rssi_mean']} dBm)")
            if q.get("nan_values"):
                bad.append(f"{q['nan_values']} NaN values in the data")
        elif q and "error" in q:
            warn.append(q["error"])
        if layout and not layout["mask_matches_config"]:
            warn.append("CSI layout differs from config.py mask: dead pairs still in use "
                        f"{layout['dead_pairs_still_used']}, excluded pairs that carry data "
                        f"{layout['excluded_pairs_with_data']} (firmware/config changed?)")
        if any(not i["recovered"] for i in self.interruptions) and status == "completed":
            warn.append("a data stall was still going on at the end of the session")
        elif self.interruptions:
            warn.append(f"{len(self.interruptions)} interruption(s) during the session")
        if self.malformed and not bad:
            warn.append(f"{self.malformed} malformed record(s) skipped")
        if self.fmt == "basic":
            info.append("no packet numbers: packet loss cannot be measured")
            info.append("no board timestamp: only the PC arrival time is available")
            info.append("no sender address: packets from other devices cannot be filtered")
        validity = "invalid" if bad else ("valid_with_warnings" if warn else "valid")
        return validity, bad, warn, info

    @staticmethod
    def _csi_layout(rec):
        """Which of the 64 complex pairs are dead in THIS session, compared with config.py."""
        import numpy as np
        from preprocess.clean import usable_subcarriers
        dead = np.where((np.abs(rec.csi) == 0).all(axis=0))[0].tolist()
        used = set(int(i) for i in usable_subcarriers())
        excluded = sorted(set(range(rec.csi.shape[1])) - used)
        still_used = sorted(set(dead) & used)
        with_data = sorted(set(excluded) - set(dead))
        return {"dead_pairs_observed": dead, "active_pairs_observed": rec.csi.shape[1] - len(dead),
                "pairs_used_by_pipeline": len(used), "excluded_by_config": excluded,
                "dead_pairs_still_used": still_used, "excluded_pairs_with_data": with_data,
                "mask_matches_config": not still_used and not with_data}

    def _write_meta(self, meta):
        base = {"session_id": self.session_id, "start_time": _iso(self.t0),
                "experiment": self.exp, "receiver": self.rx}
        base.update(meta)
        _write_json(os.path.join(self.dir, "metadata.json"), base)
