"""Central settings for the Dormant signal-processing pipeline (Member 3).

Change values HERE, not inside the other modules.
"""

# --- CSI layout (ESP32, 20 MHz, LLTF only: 128 ints = 64 complex subcarriers) ---
N_SUBCARRIERS = 64

# ESP32 CSI buffer order is [imag0, real0, imag1, real1, ...] per the ESP-IDF docs.
# If your plots look wrong, try "real_imag" -- amplitude is unaffected, phase is.
IQ_ORDER = "imag_real"

# Subcarrier indices (0..63) that are always zero in your sample (guard band / DC).
NULL_SUBCARRIERS = list(range(28, 37))
# Index 0 shows amplitude ~141 vs ~10 elsewhere -> looks like a DC/LO artifact.
DROP_SUBCARRIER_0 = True

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
