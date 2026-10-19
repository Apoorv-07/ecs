"""Record one controlled CSI session (folder + metadata + log + quality verdict).

Before a session (is the receiver alive and sending good CSI?):
    python scripts/record_session.py --preflight --port COM10

Record (stop with Ctrl+C or let --duration end it):
    python scripts/record_session.py --port COM10 --condition paced_breathing ^
        --participant P01 --reference-bpm 12 --duration 240 ^
        --rx-firmware "Dormant_RX 2026-10-08" --notes "lying on back, metronome 12/min"

Test the whole chain without hardware:
    python scripts/record_session.py --simulate --condition test --duration 70
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingest.recorder import SerialSource, SimSource, SessionRecorder, preflight, SourceError


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--port", default="COM10", help="serial port of the receiver (default COM10)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--out", default="dataset/raw", help="folder that holds the sessions")
    ap.add_argument("--condition", help="what is happening, e.g. empty_room, paced_breathing "
                                        "(you decide; the recorder never guesses labels)")
    ap.add_argument("--participant", help="non-identifying code such as P01")
    ap.add_argument("--reference-bpm", type=float, help="true breathing rate if known (metronome)")
    ap.add_argument("--notes", help="free text: position, events with clock times...")
    ap.add_argument("--setup-notes", help="TX/RX positions, distance, room")
    ap.add_argument("--rx-firmware", help="receiver firmware name/version")
    ap.add_argument("--tx-firmware", help="transmitter firmware name/version")
    ap.add_argument("--duration", type=float, help="stop automatically after N seconds")
    ap.add_argument("--mac", help="keep only packets from this sender (needs the extended format)")
    ap.add_argument("--session-id", help="default: next free session_NNN")
    ap.add_argument("--reconnect-s", type=float, default=60.0)
    ap.add_argument("--stall-s", type=float, default=10.0)
    ap.add_argument("--preflight", action="store_true", help="only check that data arrives")
    ap.add_argument("--simulate", action="store_true", help="fake receiver (no hardware)")
    a = ap.parse_args()

    src = SimSource(realtime=True) if a.simulate else SerialSource(a.port, a.baud)

    if a.preflight:
        try:
            r = preflight(src, seconds=5)
        except SourceError as e:
            sys.exit(f"FAILED: {e}\nCheck the COM port, close idf.py monitor, and replug the receiver.")
        print(r)
        print("OK: CSI data is arriving." if r["ok"] else
              "NOT OK: no (or mostly damaged) CSI data. Check the receiver and transmitter.")
        sys.exit(0 if r["ok"] else 1)

    if not a.condition:
        ap.error("--condition is required (e.g. --condition empty_room)")

    rec = SessionRecorder(src, a.out, condition=a.condition, participant=a.participant,
                          notes=a.notes, reference_bpm=a.reference_bpm, rx_firmware=a.rx_firmware,
                          tx_firmware=a.tx_firmware, setup_notes=a.setup_notes,
                          port=None if a.simulate else a.port, baud=a.baud, mac_filter=a.mac,
                          session_id=a.session_id, duration_s=a.duration,
                          reconnect_s=a.reconnect_s, stall_s=a.stall_s)
    print(f"Recording {rec.session_id} -> {rec.dir}   (Ctrl+C to stop)")
    meta = rec.run()
    print(f"\n{meta['session_id']}: {meta['validity'].upper()}  "
          f"({meta['counts']['records_saved']} records, {meta['duration_s']} s)")
    for k in ("validity_reasons", "warnings", "info"):
        for m in meta[k]:
            print(f"  [{k.split('_')[0]}] {m}")
    print("Files:", rec.dir)


if __name__ == "__main__":
    main()
