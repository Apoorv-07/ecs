# Member 4: Movement Detection and Event Extraction

## 1. Purpose

Member 4 consumes the motion features produced by Member 3 and performs
three processing stages:

1. Movement-window classification.
2. Movement-intensity classification.
3. Timestamped candidate-event extraction.

The current implementation is threshold-based. It does not train a
deep-learning model and does not independently prove that a detected
event is a body turn or bed exit.

## 2. Pipeline

Member 3 motion_features.csv
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

## 3. Files

- movement_detector.py
  Classifies usable windows as movement_candidate or still_candidate.
  Unreliable windows can be classified as unknown.

- movement_intensity.py
  Assigns low, medium, or high intensity to movement candidates.
  Still windows receive not_applicable; unreliable windows can receive
  unknown.

- event_detector.py
  Groups consecutive valid movement-candidate windows into events
  according to duration and gap rules.

## 4. Current experimental defaults

| Parameter | Default | Purpose |
|---|---:|---|
| Movement threshold | 0.30 | Movement-window classification |
| Low-intensity threshold | 0.30 | Lower intensity boundary |
| High-intensity threshold | 0.40 | Higher intensity boundary |
| Minimum event duration | 1.0 second | Minimum duration for an event |
| Maximum event gap | 1.0 second | Maximum gap between consecutive windows |

These values are experimental defaults, not validated final thresholds.
The movement and low-intensity thresholds happen to share the same
numerical value, but they are used for different classification stages.

Thresholds must be calibrated using suitable recordings, including
empty-room, occupied-still, and controlled-movement sessions.
Evaluation should use labelled events and separate calibration and
evaluation recordings where possible.

## 5. Running the pipeline

Run these commands from the project root.

Example input: an existing Member 3 motion-features CSV.

### Stage 1: Movement detection

    python member4/movement_detector.py --input "outputs/member4_review/S06_position_changes/motion_features.csv" --output "outputs/member4_integration_test/S06_movement.csv" --threshold 0.30

### Stage 2: Movement intensity

    python member4/movement_intensity.py --input "outputs/member4_integration_test/S06_movement.csv" --output "outputs/member4_integration_test/S06_intensity.csv" --low-threshold 0.30 --high-threshold 0.40

### Stage 3: Candidate-event extraction

    python member4/event_detector.py --input "outputs/member4_integration_test/S06_intensity.csv" --output "outputs/member4_integration_test/S06_events.csv" --min-duration 1.0 --max-gap 1.0

The example paths are local to the current project and require the
specified input file to exist. Output directories are created as needed.

## 6. Output interpretation

The movement output retains the timestamps, motion score, status, and
movement classifications.

The intensity output includes movement intensity labels.

The event output includes:

- event_id
- event_type
- start_time
- end_time
- duration_s
- window_count
- peak_motion_score
- peak_intensity

Event timestamps use the packet-clock time represented in the input CSV.
The event type is movement_candidate, not a confirmed physiological or
sleep event.

Member 5 or Member 6 should confirm the downstream interface before
depending on these outputs in a larger pipeline.

## 7. Handling unreliable data

Member 3 marks unusable windows with a non-ok status or a missing motion
score. These must not be interpreted as proof that the person is still.
The detector should preserve the distinction between still and unknown.

Event grouping breaks when an unusable window interrupts a sequence or
when the gap between consecutive windows exceeds the configured limit.

## 8. Tests

Run the Member 4 tests:

    python -m pytest tests/test_member4.py -v

Run the full project test suite:

    python -m pytest -v

At the time of this documentation, all 40 project tests passed, including
the three Member 4 tests. Re-run the tests after any code changes.

## 9. Preliminary evaluation and limitations

The initial review covered seven sessions: empty room, occupied still,
walking, lying on the back, lying on the left side, position changes,
and natural rest.

The current review produced candidate events even in the empty-room
session. Therefore, false positives remain a concern.

The review recordings do not provide sufficient labelled event
timestamps to establish reliable event precision, recall, or F1 score.
The current results should be treated as preliminary, not as validated
detection performance.

The threshold values and duration rules require further calibration and
evaluation before claims about body turns, bed exits, or sleep events
can be made.
