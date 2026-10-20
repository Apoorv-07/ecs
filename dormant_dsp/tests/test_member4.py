
import pandas as pd
import pytest

from member4.movement_intensity import classify_intensity


def test_intensity_classification(tmp_path):
    """Check intensity levels and still-candidate handling."""

    input_csv = tmp_path / "movement.csv"
    output_csv = tmp_path / "intensity.csv"

    df = pd.DataFrame({
        "motion_score": [0.20, 0.30, 0.40, 0.25, None],
        "status": ["ok", "ok", "ok", "ok", "low_coverage"],
        "movement_status_smoothed": [
            "movement_candidate",
            "movement_candidate",
            "movement_candidate",
            "still_candidate",
            "unknown",
        ],
    })

    df.to_csv(input_csv, index=False)

    classify_intensity(
        input_csv=str(input_csv),
        output_csv=str(output_csv),
    )

    result = pd.read_csv(output_csv)

    assert result.loc[0, "movement_intensity"] == "low"
    assert result.loc[1, "movement_intensity"] == "medium"
    assert result.loc[2, "movement_intensity"] == "high"
    assert result.loc[3, "movement_intensity"] == "not_applicable"
    assert result.loc[4, "movement_intensity"] == "unknown"


def test_invalid_thresholds(tmp_path):
    """The high threshold must exceed the low threshold."""

    input_csv = tmp_path / "movement.csv"
    output_csv = tmp_path / "intensity.csv"

    pd.DataFrame({
        "motion_score": [0.35],
        "status": ["ok"],
        "movement_status_smoothed": ["movement_candidate"],
    }).to_csv(input_csv, index=False)

    with pytest.raises(ValueError):
        classify_intensity(
            input_csv=str(input_csv),
            output_csv=str(output_csv),
            low_threshold=0.40,
            high_threshold=0.30,
        )


def test_missing_input_file(tmp_path):
    """A missing input file should raise FileNotFoundError."""

    with pytest.raises(FileNotFoundError):
        classify_intensity(
            input_csv=str(tmp_path / "missing.csv"),
            output_csv=str(tmp_path / "output.csv"),
        )
