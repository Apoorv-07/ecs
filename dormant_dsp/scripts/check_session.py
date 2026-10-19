"""Re-check a saved session: raw log vs csv, quality report; optionally record a manual review.

    python scripts/check_session.py dataset/raw/session_001
    python scripts/check_session.py dataset/raw/session_001 --review invalid --comment "person coughed, restarted"
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ingest.recorder import verify_session, _write_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session_dir")
    ap.add_argument("--review", choices=["valid", "invalid"], help="your own verdict (saved in metadata.json)")
    ap.add_argument("--comment", default="")
    a = ap.parse_args()

    mp = os.path.join(a.session_dir, "metadata.json")
    meta = json.load(open(mp, encoding="utf-8"))
    v = verify_session(a.session_dir, meta.get("receiver", {}).get("mac_filter"))
    print("raw log vs csv:", v)
    print("recorder verdict:", meta.get("validity"), meta.get("validity_reasons"))
    csv_path = os.path.join(a.session_dir, "csi_data.csv")
    if os.path.exists(csv_path):
        from ingest.parser import load_csv, validate
        print(json.dumps(validate(load_csv(csv_path)), indent=2))
    if a.review:
        meta["manual_review"] = {"verdict": a.review, "comment": a.comment}
        _write_json(mp, meta)
        print("Saved manual review:", a.review)


if __name__ == "__main__":
    main()
