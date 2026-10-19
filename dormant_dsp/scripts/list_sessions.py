"""One table of all recorded sessions (also saved as dataset/sessions_index.csv for Member 5).

    python scripts/list_sessions.py            (default folder dataset/raw)
"""
import csv, glob, json, os, sys

root = sys.argv[1] if len(sys.argv) > 1 else "dataset/raw"
rows = []
for mp in sorted(glob.glob(os.path.join(root, "session_*", "metadata.json"))):
    m = json.load(open(mp, encoding="utf-8"))
    e, c, q = m.get("experiment", {}), m.get("counts", {}), m.get("quality") or {}
    rev = (m.get("manual_review") or {}).get("verdict", "")
    rows.append({"session": m["session_id"], "start": m.get("start_time", ""),
                 "condition": e.get("condition", ""), "participant": e.get("participant_code", ""),
                 "reference_bpm": e.get("reference_bpm", ""), "duration_s": m.get("duration_s", ""),
                 "records": c.get("records_saved", ""), "rate_hz": q.get("mean_rate_hz", ""),
                 "validity": m.get("validity", m.get("status", "")), "manual_review": rev,
                 "notes": (e.get("notes") or "")[:60]})
if not rows:
    sys.exit(f"No sessions found in {root}")
keys = list(rows[0])
print("  ".join(f"{k:<14}" if k != "notes" else k for k in keys))
for r in rows:
    print("  ".join(f"{str(r[k]):<14}"[:14] if k != "notes" else str(r[k]) for k in keys))
out = os.path.join(os.path.dirname(root.rstrip("/\\")) or ".", "sessions_index.csv")
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
print("\nSaved ->", out)
