# Member 4: Movement Detection and Event Extraction

## 1. Purpose

Member 4 consumes the motion features produced by Member 3 and performs three processing stages:

1. Movement-window classification.
2. Movement-intensity classification.
3. Timestamped candidate-event extraction.

The current implementation is threshold-based. It does not train a deep-learning model and does not independently prove that a detected event is a body turn or bed exit.

## 2. Pipeline

```text
Member 3: motion_features.csv
              |
              v
     movement_detector.py
              |
              v
 Movement and still classifications
              |
              v
     movement_intensity.py
              |
              v
      Movement-intensity labels
              |
              v
       event_detector.py
              |
              v
   Timestamped candidate movement events
```

## 3. Files

- `movement_detector.py`  
  Classifies usable windows as `movement_candidate` or `still_candidate`. Unreliable windows can be classified as `unknown`.

- `movement_intensity.py`  
  Assigns `low`, `medium`, or `high` intensity to movement candidates. Still windows receive `not_applicable`; unreliable windows can receive `unknown`.

- `event_detector.py`  
  Groups consecutive valid movement-candidate windows into events according to duration and gap rules.

- `occupancy_detector.py`  
  An additional experimental component that uses RSSI mean and data-quality information to produce occupancy candidates.

## 4. Current Experimental Defaults

| Parameter | Default | Purpose |
|---|---:|---|
| Movement threshold | 0.30 | Movement-window classification |
| Low-intensity threshold | 0.30 | Lower intensity boundary |
| High-intensity threshold | 0.40 | Higher intensity boundary |
| Minimum event duration | 1.0 second | Minimum duration for an event |
| Maximum event gap | 1.0 second | Maximum gap between consecutive windows |

These values are experimental defaults, not validated final thresholds.

The movement and low-intensity thresholds happen to share the same numerical value, but they are used for different classification stages.

Thresholds must be calibrated using suitable recordings, including empty-room, occupied-still, and controlled-movement sessions. Evaluation should use labelled events and separate calibration and evaluation recordings where possible.

## 5. Running the Movement Pipeline

Run these commands from the project root.

Example input: an existing Member 3 motion-features CSV.

### Stage 1: Movement Detection

```powershell
python member4/movement_detector.py --input "outputs/member4_review/S06_position_changes/motion_features.csv" --output "outputs/member4_integration_test/S06_movement.csv" --threshold 0.30
```

This stage classifies each usable window as a movement candidate or a still candidate. Unreliable windows remain unknown.

### Stage 2: Movement Intensity

```powershell
python member4/movement_intensity.py --input "outputs/member4_integration_test/S06_movement.csv" --output "outputs/member4_integration_test/S06_intensity.csv" --low-threshold 0.30 --high-threshold 0.40
```

This stage assigns intensity labels to movement candidates.

### Stage 3: Candidate-Event Extraction

```powershell
python member4/event_detector.py --input "outputs/member4_integration_test/S06_intensity.csv" --output "outputs/member4_integration_test/S06_events.csv" --min-duration 1.0 --max-gap 1.0
```

This stage groups qualifying movement windows into timestamped candidate events.

The example paths are local to the current project and require the specified input file to exist. Output directories are created as needed.

## 6. Output Interpretation

The movement output retains the timestamps, motion score, status, and movement classifications.

The intensity output includes movement-intensity labels.

The event output includes:

- `event_id`
- `event_type`
- `start_time`
- `end_time`
- `duration_s`
- `window_count`
- `peak_motion_score`
- `peak_intensity`

Event timestamps use the packet-clock time represented in the input CSV.

The event type is `movement_candidate`, not a confirmed physiological or sleep event.

Member 5 or Member 6 should confirm the downstream interface before depending on these outputs in a larger pipeline.

## 7. Handling Unreliable Data

Member 3 marks unusable windows with a non-`ok` status or a missing motion score. These must not be interpreted as proof that the person is still.

The detector should preserve the distinction between `still` and `unknown`.

Event grouping breaks when an unusable window interrupts a sequence or when the gap between consecutive windows exceeds the configured limit.

## 8. Tests

Run the Member 4 tests:

```powershell
python -m pytest tests/test_member4.py -v
```

Run the full project test suite:

```powershell
python -m pytest -v
```

At the time of this documentation, all 40 project tests passed, including the three Member 4 tests. Re-run the tests after any code changes.

## 9. Preliminary Evaluation and Limitations

The initial review covered seven sessions:

- S01: Empty room
- S02: Occupied still
- S03: Walking
- S04: Lying on back
- S05: Lying on left side
- S06: Position changes
- S07: Natural rest

The initial review produced candidate events even in the empty-room session. Therefore, false positives remain a concern.

The review recordings do not provide sufficient labelled event timestamps to establish reliable event precision, recall, or F1 score. The current results should be treated as preliminary, not as validated detection performance.

The threshold values and duration rules require further calibration and evaluation before claims about body turns, bed exits, or sleep events can be made.

## 10. Experimental Occupancy Detection

The occupancy detector is an additional Member 4 component. It uses the RSSI mean feature from Member 3's `motion_features.csv` to classify each window as an occupancy candidate.

### File

- `occupancy_detector.py`

### Classification Rules

| Condition | Output |
|---|---|
| RSSI mean <= -38 dBm | `empty_candidate` |
| RSSI mean >= -33 dBm | `occupied_candidate` |
| RSSI between -38 and -33 dBm | `unknown` |
| Poor data quality or invalid RSSI | `unknown` |

The detector also checks the `valid_frac` feature when it is available. Windows with `valid_frac` below `0.80` are classified as unknown.

These thresholds are experimental and have not been validated on independent recordings.

### Temporal Smoothing

A three-window majority vote is applied to the raw classifications.

- Unknown windows do not vote.
- Windows originally classified as unknown remain unknown.
- If the valid neighboring votes are tied, the smoothed label becomes unknown.

The output CSV contains:

- `occupancy_status_raw`: classification before smoothing.
- `occupancy_status`: classification after smoothing.
- `occupancy_reason`: reason for the original classification.

### Running Occupancy Detection

Run these commands from the project root.

**Example: Empty-room recording**

```powershell
python member4/occupancy_detector.py --input "outputs/member4_review/S01_empty_room/motion_features.csv" --output "outputs/member4_review/S01_empty_room/occupancy_results_smoothed.csv"
```

**Example: Occupied-still recording**

```powershell
python member4/occupancy_detector.py --input "outputs/member4_review/S02_occupied_still/motion_features.csv" --output "outputs/member4_review/S02_occupied_still/occupancy_results_smoothed.csv"
```

### Preliminary Occupancy Review

The seven reviewed recordings contain 2,072 windows in total.

| Session | Recording | Smoothed output |
|---|---|---|
| S01 | Empty room | 296 empty candidates |
| S02 | Occupied still | 296 occupied candidates |
| S03 | Walking | 296 occupied candidates |
| S04 | Lying on back | 296 occupied candidates |
| S05 | Lying on left side | 296 occupied candidates |
| S06 | Position changes | 296 occupied candidates |
| S07 | Natural rest | 296 occupied candidates |

In these recordings, the smoothed classifications matched the raw classifications for every window.

These counts describe the detector's output, not verified accuracy. The thresholds were explored using these recordings, so independent sessions and reliable occupancy labels are needed for proper evaluation.

RSSI can also change because of environmental and hardware conditions.

Occupancy candidates must not be treated as confirmed ground truth. The downstream interface should be agreed upon with Member 5 before integrating this output into the complete system.
