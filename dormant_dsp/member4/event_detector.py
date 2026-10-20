
import argparse
from pathlib import Path

import pandas as pd


def detect_events(
    input_csv: str,
    output_csv: str,
    min_duration: float = 1.0,
    max_gap: float = 1.0,
) -> None:
    """
    Group consecutive usable movement windows into candidate events.

    These are experimental movement events, not confirmed body turns
    or bed exits. Thresholds and duration rules require labelled data.
    """

    input_path = Path(input_csv)
    output_path = Path(output_csv)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if min_duration < 0:
        raise ValueError("min_duration must be non-negative.")

    if max_gap < 0:
        raise ValueError("max_gap must be non-negative.")

    df = pd.read_csv(input_path)

    required = {
        "t_start",
        "t_end",
        "motion_score",
        "status",
        "movement_status_smoothed",
        "movement_intensity",
    }

    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df["t_start"] = pd.to_numeric(df["t_start"], errors="coerce")
    df["t_end"] = pd.to_numeric(df["t_end"], errors="coerce")
    df["motion_score"] = pd.to_numeric(
        df["motion_score"], errors="coerce"
    )

    df = df.sort_values("t_start").reset_index(drop=True)

    events = []
    active = []

    def save_event(rows):
        if not rows:
            return

        start = float(rows[0]["t_start"])
        end = float(max(row["t_end"] for row in rows))
        duration = end - start

        if duration < min_duration:
            return

        scores = [
            float(row["motion_score"])
            for row in rows
            if pd.notna(row["motion_score"])
        ]

        intensities = [
            row["movement_intensity"]
            for row in rows
            if row["movement_intensity"] in ("low", "medium", "high")
        ]

        if "high" in intensities:
            peak_intensity = "high"
        elif "medium" in intensities:
            peak_intensity = "medium"
        elif "low" in intensities:
            peak_intensity = "low"
        else:
            peak_intensity = "unknown"

        events.append({
            "event_id": len(events) + 1,
            "event_type": "movement_candidate",
            "start_time": start,
            "end_time": end,
            "duration_s": duration,
            "window_count": len(rows),
            "peak_motion_score": max(scores) if scores else float("nan"),
            "peak_intensity": peak_intensity,
        })

    for _, row in df.iterrows():
        valid = (
            pd.notna(row["t_start"])
            and pd.notna(row["t_end"])
            and row["t_end"] >= row["t_start"]
            and row["status"] == "ok"
            and pd.notna(row["motion_score"])
            and row["movement_status_smoothed"] == "movement_candidate"
        )

        if not valid:
            save_event(active)
            active = []
            continue

        current = row.to_dict()

        if active:
            previous_end = float(active[-1]["t_end"])
            gap = float(current["t_start"]) - previous_end

            if gap > max_gap:
                save_event(active)
                active = []

        active.append(current)

    save_event(active)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = pd.DataFrame(
        events,
        columns=[
            "event_id",
            "event_type",
            "start_time",
            "end_time",
            "duration_s",
            "window_count",
            "peak_motion_score",
            "peak_intensity",
        ],
    )
    result.to_csv(output_path, index=False)

    print("=" * 50)
    print("MEMBER 4 - EVENT DETECTOR")
    print("=" * 50)
    print(f"Input: {input_path}")
    print(f"Output: {output_path}")
    print(f"Minimum duration: {min_duration:.2f} s")
    print(f"Maximum gap: {max_gap:.2f} s")
    print(f"Candidate events detected: {len(result)}")

    if not result.empty:
        print("\nFirst 10 events:")
        print(result.head(10).to_string(index=False))
    else:
        print("No candidate events met the minimum duration.")

    print("\nProcessing completed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Group movement windows into candidate events"
    )
    parser.add_argument(
        "--input",
        default="outputs/member4_intensity.csv",
    )
    parser.add_argument(
        "--output",
        default="outputs/member4_events.csv",
    )
    parser.add_argument("--min-duration", type=float, default=1.0)
    parser.add_argument("--max-gap", type=float, default=1.0)

    args = parser.parse_args()

    detect_events(
        input_csv=args.input,
        output_csv=args.output,
        min_duration=args.min_duration,
        max_gap=args.max_gap,
    )
