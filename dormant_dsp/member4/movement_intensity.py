
import argparse
from pathlib import Path

import pandas as pd


def classify_intensity(
    input_csv: str,
    output_csv: str,
    low_threshold: float = 0.30,
    high_threshold: float = 0.40,
) -> None:
    """
    Assign preliminary movement intensity levels from motion_score.

    Experimental rules:
        Still candidate:
            not_applicable

        Movement candidate with score < low_threshold:
            low

        low_threshold <= score < high_threshold:
            medium

        score >= high_threshold:
            high

        Unreliable windows:
            unknown

    These thresholds are experimental and must be calibrated
    using labelled recordings before real-world use.
    """

    input_path = Path(input_csv)
    output_path = Path(output_csv)

    # Validate the input file.
    if not input_path.exists():
        raise FileNotFoundError(
            f"Input file not found: {input_path}"
        )

    # Validate thresholds.
    if low_threshold < 0:
        raise ValueError(
            "Low threshold must be non-negative."
        )

    if high_threshold <= low_threshold:
        raise ValueError(
            "High threshold must be greater than low threshold."
        )

    # Load the movement detector output.
    df = pd.read_csv(input_path)

    required_columns = {
        "motion_score",
        "status",
        "movement_status_smoothed",
    }

    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    # Convert motion scores to numeric values.
    # Invalid values become NaN.
    df["motion_score"] = pd.to_numeric(
        df["motion_score"],
        errors="coerce",
    )

    # Accept only usable windows with finite motion scores.
    usable = (
        df["status"].eq("ok")
        & df["motion_score"].notna()
        & df["motion_score"].map(
            lambda x: float("-inf") < x < float("inf")
            if pd.notna(x)
            else False
        )
        & df["movement_status_smoothed"].isin(
            [
                "movement_candidate",
                "still_candidate",
            ]
        )
    )

    # Default: unreliable windows remain unknown.
    df["movement_intensity"] = "unknown"

    # Still candidates do not receive movement intensity.
    still = (
        usable
        & df["movement_status_smoothed"].eq(
            "still_candidate"
        )
    )

    df.loc[
        still,
        "movement_intensity",
    ] = "not_applicable"

    # Assign intensity only to movement candidates.
    moving = (
        usable
        & df["movement_status_smoothed"].eq(
            "movement_candidate"
        )
    )

    # Low intensity is the default for usable movement candidates.
    df.loc[
        moving,
        "movement_intensity",
    ] = "low"

    # Medium intensity.
    df.loc[
        moving
        & (df["motion_score"] >= low_threshold),
        "movement_intensity",
    ] = "medium"

    # High intensity.
    df.loc[
        moving
        & (df["motion_score"] >= high_threshold),
        "movement_intensity",
    ] = "high"

    # Create the output directory if it does not exist.
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Save the results.
    df.to_csv(
        output_path,
        index=False,
    )

    # Print the processing summary.
    print("=" * 55)
    print("MEMBER 4 - MOVEMENT INTENSITY")
    print("=" * 55)

    print(f"Input file:       {input_path}")
    print(f"Output file:      {output_path}")
    print(f"Low threshold:    {low_threshold:.3f}")
    print(f"High threshold:   {high_threshold:.3f}")
    print(f"Total windows:    {len(df)}")
    print(f"Usable windows:   {int(usable.sum())}")
    print(f"Unknown windows:  {int((~usable).sum())}")

    print("\nIntensity counts:")

    intensity_order = [
        "low",
        "medium",
        "high",
        "not_applicable",
        "unknown",
    ]

    print(
        df["movement_intensity"]
        .value_counts()
        .reindex(
            intensity_order,
            fill_value=0,
        )
        .to_string()
    )

    print("\nFirst 10 results:")

    columns_to_show = [
        col
        for col in [
            "t_start",
            "t_end",
            "motion_score",
            "movement_status_smoothed",
            "movement_intensity",
        ]
        if col in df.columns
    ]

    print(
        df[columns_to_show]
        .head(10)
        .to_string(index=False)
    )

    print("\nProcessing completed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Classify preliminary CSI movement intensity"
        )
    )

    parser.add_argument(
        "--input",
        default="outputs/member4_movement.csv",
        help="Input Member 4 movement CSV",
    )

    parser.add_argument(
        "--output",
        default="outputs/member4_intensity.csv",
        help="Output intensity CSV",
    )

    parser.add_argument(
        "--low-threshold",
        type=float,
        default=0.30,
        help="Experimental lower intensity threshold",
    )

    parser.add_argument(
        "--high-threshold",
        type=float,
        default=0.40,
        help="Experimental upper intensity threshold",
    )

    args = parser.parse_args()

    classify_intensity(
        input_csv=args.input,
        output_csv=args.output,
        low_threshold=args.low_threshold,
        high_threshold=args.high_threshold,
    )
