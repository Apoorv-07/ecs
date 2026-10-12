"""Quick diagnostic plots."""
import numpy as np
import matplotlib
matplotlib.use("Agg")  # no window; saves to file
import matplotlib.pyplot as plt


def overview(rec, pre, save_path: str):
    fig, ax = plt.subplots(2, 2, figsize=(14, 9))

    im = ax[0, 0].imshow(pre["amp"].T, aspect="auto", origin="lower",
                         extent=[pre["t"][0], pre["t"][-1], 0, pre["amp"].shape[1]])
    ax[0, 0].set(title="Amplitude (cleaned, resampled)", xlabel="time (s)", ylabel="subcarrier #")
    fig.colorbar(im, ax=ax[0, 0])

    ax[0, 1].plot(rec.t, rec.rssi, lw=0.8)
    ax[0, 1].set(title="RSSI", xlabel="time (s)", ylabel="dBm")

    dt = np.diff(rec.t) * 1000
    dt = dt[dt > 0]
    ax[1, 0].hist(dt, bins=np.logspace(np.log10(max(dt.min(), 1)), np.log10(dt.max()), 40))
    ax[1, 0].set(xscale="log", title="Inter-packet gap (host clock)", xlabel="ms", ylabel="count")

    j = pre["amp"].shape[1] // 2
    o = pre["outliers"][:, j]
    ax[1, 1].plot(pre["t_pkt"], pre["amp_pkt"][:, j], ".", ms=3, alpha=0.5, label="raw packets")
    ax[1, 1].plot(pre["t_pkt"][o], pre["amp_pkt"][o, j], "rx", label="Hampel outliers")
    ax[1, 1].plot(pre["t"], pre["amp"][:, j], lw=1, label="cleaned + resampled")
    ax[1, 1].set(title=f"Subcarrier {pre['subcarriers'][j]}", xlabel="time (s)")
    ax[1, 1].legend()

    fig.tight_layout()
    fig.savefig(save_path, dpi=110)
    plt.close(fig)
