
"""Central settings for the Dormant signal-processing pipeline (Member 3).

Change values HERE, not inside the other modules.
"""

# --- CSI layout (ESP32, 20 MHz, LLTF only: 128 ints = 64 complex subcarriers) ---
N_SUBCARRIERS = 64

# ESP32 CSI buffer order is [imag0, real0, imag1, real1, ...] per the ESP-IDF docs.
# If your plots look wrong, try "real_imag" -- amplitude is unaffected, phase is.
IQ_ORDER = "imag_real"

# Complex pairs (0..63) that carry no data for the CURRENT firmware (Arduino RX, LLTF, 20 MHz, channel 1).
# Verified on S01-S07: byte columns 1-4 (pairs 0,1: zeroed by the RX when first_word_invalid) and
# 55-76 (pairs 27..37: null/guard tones) are ALWAYS zero -> 13 dead pairs, 51 active pairs
# (0-based indices 2..26 and 38..63). The older ESP-IDF firmware had a different pattern
# (pairs 28..36 zero, pair 0 huge): recordings from it need the old mask.
# The recorder checks every session against this mask and warns when they disagree.
NULL_SUBCARRIERS = [1] + list(range(27, 38))
DROP_SUBCARRIER_0 = True      # pair 0 is always zeroed (first_word_invalid) -> dropped together with NULL_SUBCARRIERS

# --- Timing ---
TARGET_FS = 10.0      # Hz, uniform rate after resampling (TX sends at 10 Hz)
MAX_GAP_S = 1.0       # gaps longer than this are flagged as "not trustworthy"
GAP_WARN_S = 0.3      # used in the validation report

# --- Hampel filter ---
HAMPEL_WINDOW = 7     # samples (odd)
HAMPEL_SIGMAS = 3.0

# --- Respiration (Days 11-30) ---
BREATH_BAND_HZ = (0.1, 0.5)   # 6-30 breaths/min
MIN_BPM, MAX_BPM = 6, 30
BP_ORDER = 4                  # Butterworth order
PCA_N = 5                     # components examined when picking the breathing one
WINDOW_S = 60                 # analysis window (needs >= ~3 breaths at the slowest rate)
HOP_S = 10                    # how often a new estimate is produced

# A breathing rate is only passed on as "trusted" when the breathing-band spectrum has one clear peak.
# Calibrated on negative controls (white noise and the empty-room recording S01: 95% of their windows
# are below 0.54), so about 5% false alarms. PROVISIONAL until the paced-breathing session (S08) exists.
MIN_PEAK_RATIO = 0.6
