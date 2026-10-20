
import argparse
import csv
from collections import Counter
from pathlib import Path


EMPTY_RSSI_THRESHOLD = -38.0
OCCUPIED_RSSI_THRESHOLD = -33.0
MIN_VALID_FRACTION = 0.80
SMOOTHING_WINDOW = 3

LABELS = (
    "occupied_candidate",
    "empty_candidate",
    "unknown",
)


def classify_window(row):
    """Classify one window using experimental RSSI thresholds."""

    quality_status = row.get("status", "").strip().lower()

    if quality_status and quality_status != "ok":
        return "unknown", "poor_data_quality"

    try:
        rssi = float(row["rssi_mean"])
    except (KeyError, TypeError, ValueError):
        return "unknown", "missing_or_invalid_rssi"

    if rssi != rssi or abs(rssi) == float("inf"):
        return "unknown", "invalid_rssi"

    valid_fraction = row.get("valid_frac", "").strip()

    if valid_fraction:
        try:
            valid_fraction = float(valid_fraction)
        except ValueError:
            return "unknown", "invalid_quality_value"

        if (
            not 0.0 <= valid_fraction <= 1.0
            or valid_fraction != valid_fraction
        ):
            return "unknown", "invalid_quality_value"

        if valid_fraction < MIN_VALID_FRACTION:
            return "unknown", "low_valid_fraction"

    if rssi <= EMPTY_RSSI_THRESHOLD:
        return "empty_candidate", "rssi_supports_empty"

    if rssi >= OCCUPIED_RSSI_THRESHOLD:
        return "occupied_candidate", "rssi_supports_occupied"

    return "unknown", "rssi_in_uncertain_range"


def smooth_labels(labels, window_size=SMOOTHING_WINDOW):
    """
    Smooth labels with a local majority vote.

    Unknown labels do not vote for either occupancy state.
    Ties remain unknown. Existing unknown windows remain unknown.
    """

    if window_size < 1 or window_size % 2 == 0:
        raise ValueError("Smoothing window size must be a positive odd number.")

    radius = window_size // 2
    smoothed = []

    for index, original_label in enumerate(labels):
        if original_label == "unknown":
            smoothed.append("unknown")
            continue

        start = max(0, index - radius)
        end = min(len(labels), index + radius + 1)

        neighbors = labels[start:end]
        votes = Counter(
            label for label in neighbors
            if label in ("empty_candidate", "occupied_candidate")
        )

        empty_votes = votes["empty_candidate"]
        occupied_votes = votes["occupied_candidate"]

        if empty_votes > occupied_votes:
            smoothed.append("empty_candidate")
        elif occupied_votes > empty_votes:
            smoothed.append("occupied_candidate")
        else:
            smoothed.append("unknown")

    return smoothed


def process_file(input_path, output_path):
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.is_file():
        raise FileNotFoundError(f"Input CSV not found: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames or "rssi_mean" not in reader.fieldnames:
            raise ValueError("Input CSV must contain an rssi_mean column.")

        original_fields = list(reader.fieldnames)
        rows = list(reader)

    raw_labels = []
    reasons = []

    for row in rows:
        label, reason = classify_window(row)
        raw_labels.append(label)
        reasons.append(reason)

    smoothed_labels = smooth_labels(raw_labels)

    output_fields = original_fields + [
        "occupancy_status_raw",
        "occupancy_status",
        "occupancy_reason",
    ]

    raw_counts = Counter(raw_labels)
    smoothed_counts = Counter(smoothed_labels)

    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=output_fields)
        writer.writeheader()

        for row, raw_label, smoothed_label, reason in zip(
            rows, raw_labels, smoothed_labels, reasons
        ):
            row["occupancy_status_raw"] = raw_label
            row["occupancy_status"] = smoothed_label
            row["occupancy_reason"] = reason
            writer.writerow(row)

    print("\nMEMBER 4 - OCCUPANCY DETECTOR")
    print("=" * 40)
    print(f"Input:  {input_path}")
    print(f"Output: {output_path}")
    print(f"Windows processed: {len(rows)}")
    print(f"Smoothing window: {SMOOTHING_WINDOW} windows")
    print(f"Empty threshold: <= {EMPTY_RSSI_THRESHOLD} dBm")
    print(f"Occupied threshold: >= {OCCUPIED_RSSI_THRESHOLD} dBm")

    print("\nRaw classifications:")
    for label in LABELS:
        print(f"  {label}: {raw_counts[label]}")

    print("\nSmoothed classifications:")
    for label in LABELS:
        print(f"  {label}: {smoothed_counts[label]}")

    print("\nLabels are experimental candidates, not verified occupancy.")


def main():
    parser = argparse.ArgumentParser(
        description="Experimental CSI-based occupancy candidate detector."
    )
    parser.add_argument("--input", required=True, help="Input motion_features.csv")
    parser.add_argument("--output", required=True, help="Output occupancy CSV")

    args = parser.parse_args()
    process_file(args.input, args.output)


if __name__ == "__main__":
    main()
