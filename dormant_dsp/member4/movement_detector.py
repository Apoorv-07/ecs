
import argparse
from pathlib import Path

import pandas as pd


def smooth_movement_labels(df: pd.DataFrame) -> pd.DataFrame:
    """
    Smooth isolated classification changes.

    A label is changed only when:
    - The current label is known.
    - The previous and next labels are identical.
    - The current label differs from its neighbours.

    Unknown labels are never smoothed into movement or stillness.
    """
    df = df.copy()

    labels = df["movement_status"].tolist()
    smoothed = labels.copy()

    for i in range(1, len(labels) - 1):
        previous_label = labels[i - 1]
        current_label = labels[i]
        next_label = labels[i + 1]

        if (
            current_label != "unknown"
            and previous_label != "unknown"
            and next_label != "unknown"
            and previous_label == next_label
            and current_label != previous_label
        ):
            smoothed[i] = previous_label

    df["movement_status_smoothed"] = smoothed

    return df


def detect_movement(
    input_csv: str,
    output_csv: str,
    threshold: float = 0.30,
) -> None:
    """
    Read M3 motion features, classify usable windows,
    smooth isolated label changes, and save the result.

    NOTE:
    The default threshold is experimental and must be calibrated
    using labelled recordings before real-world use.
    """
    input_path = Path(input_csv)
    output_path = Path(output_csv)

    if not input_path.exists():
        raise FileNotFoundError(
            f"Input CSV not found: {input_path}"
        )

    if threshold < 0:
        raise ValueError("Threshold must be non-negative.")

    df = pd.read_csv(input_path)

    required_columns = {
        "t_start",
        "t_end",
        "motion_score",
        "status",
    }

    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            "Input CSV is missing required columns: "
            f"{sorted(missing_columns)}"
        )

    # Convert expected numeric columns safely.
    for column in ["t_start", "t_end", "motion_score"]:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    # A window is usable only when:
    # 1. Upstream status is "ok".
    # 2. Motion score is present and finite.
    # 3. Start and end timestamps are valid.
    usable = (
        df["status"].eq("ok")
        & df["motion_score"].notna()
        & df["motion_score"].map(
            lambda value: pd.notna(value)
            and float("-inf") < value < float("inf")
        )
        & df["t_start"].notna()
        & df["t_end"].notna()
        & (df["t_end"] >= df["t_start"])
    )

    # Default to unknown: unreliable windows must not be
    # incorrectly interpreted as stillness.
    df["movement_status"] = "unknown"

    # Preliminary classifications using the experimental threshold.
    df.loc[usable, "movement_status"] = "still_candidate"

    df.loc[
        usable & (df["motion_score"] >= threshold),
        "movement_status",
    ] = "movement_candidate"

    # Smooth isolated label changes.
    df = smooth_movement_labels(df)

    # Create output folder if needed.
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(output_path, index=False)

    # Display summary.
    print("=" * 55)
    print("MEMBER 4 - MOVEMENT DETECTOR")
    print("=" * 55)

    print(f"Input file:  {input_path}")
    print(f"Output file: {output_path}")
    print(f"Threshold:   {threshold:.3f}")
    print(f"Total windows: {len(df)}")
    print(f"Usable windows: {int(usable.sum())}")
    print(f"Unknown windows: {int((~usable).sum())}")

    print("\nOriginal classifications:")
    print(
        df["movement_status"]
        .value_counts()
        .reindex(
            [
                "movement_candidate",
                "still_candidate",
                "unknown",
            ],
            fill_value=0,
        )
        .to_string()
    )

    print("\nSmoothed classifications:")
    print(
        df["movement_status_smoothed"]
        .value_counts()
        .reindex(
            [
                "movement_candidate",
                "still_candidate",
                "unknown",
            ],
            fill_value=0,
        )
        .to_string()
    )

    print("\nFirst 10 results:")
    print(
        df[
            [
                "t_start",
                "t_end",
                "motion_score",
                "status",
                "movement_status",
                "movement_status_smoothed",
            ]
        ]
        .head(10)
        .to_string(index=False)
    )

    print("\nProcessing completed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Member 4 preliminary CSI movement detector"
    )

    parser.add_argument(
        "--input",
        default="outputs/motion_features.csv",
        help="Path to M3 motion features CSV",
    )

    parser.add_argument(
        "--output",
        default="outputs/member4_movement.csv",
        help="Path for Member 4 output CSV",
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=0.30,
        help="Experimental motion-score threshold",
    )

    args = parser.parse_args()

    detect_movement(
        input_csv=args.input,
        output_csv=args.output,
        threshold=args.threshold,
    )
