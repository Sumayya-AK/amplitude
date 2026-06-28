"""
P300 visualization around probe stimulus codes (100, 101, 102), with target
(3) and irrelevant (1) shown alongside for comparison.

Why target/irrelevant are included even though you only asked about probes:
a P300 (or its absence) at the probe only means something when you can
compare it against a known-working condition (target = instructed response,
should show a strong P300) and a known-baseline condition (irrelevant = no
special meaning, should show little/no P300). See the explanation we
discussed earlier in this conversation about why target and probe are both
needed -- this script plots all three together for exactly that reason.

Expects a CSV with columns: sys_time, eeg_time, ch1..ch8, stimulus
(this is exactly what utils.EEGLogger writes when marker_stream_name is set).

Usage:
    python plot_p300_events.py sub-01_run-001_eeg_raw_log.csv
    python plot_p300_events.py sub-01_run-001_eeg_raw_log.csv --tmin -0.2 --tmax 0.8
"""

import argparse

import matplotlib.pyplot as plt
import mne
import numpy as np
import pandas as pd

# Unicorn Hybrid Black 8-channel montage (standard 10-20 positions)
CHANNEL_NAMES = ["Fz", "C3", "Cz", "C4", "Pz", "PO7", "Oz", "PO8"]

EVENT_ID = {
    "irrelevant": 1,
    "target": 3,
    "probe_1": 100,
    "probe_2": 101,
    "probe_3": 102,
}

# Colors kept consistent across all plots in this script
CONDITION_COLORS = {
    "irrelevant": "gray",
    "target": "green",
    "probe_1": "red",
    "probe_2": "orange",
    "probe_3": "purple",
}

P300_WINDOW = (0.25, 0.50)  # seconds post-stimulus, typical P300 latency range


def load_csv_as_raw(csv_path, fs=250.0):
    """
    Loads a sub-XX_run-XXX_eeg_raw_log.csv (with a 'stimulus' column) and
    builds an MNE RawArray with an added STIM channel, so mne.find_events()
    works the same way it does in signal_analysis.ipynb.
    """
    df = pd.read_csv(csv_path)

    missing = [c for c in ["ch1", "ch2", "ch3", "ch4", "ch5", "ch6", "ch7", "ch8", "stimulus"]
               if c not in df.columns]
    if missing:
        raise SystemExit(
            f"Missing expected columns {missing} in '{csv_path}'.\n"
            f"This script expects the *_eeg_raw_log.csv produced by the "
            f"updated EEGLogger with marker_stream_name set (see utils.py)."
        )

    eeg_data = df[[f"ch{i}" for i in range(1, 9)]].to_numpy().T  # shape (8, n_samples)
    # Unicorn raw stream is in raw ADC units; MNE expects volts for EEG
    # channels. We don't know the exact gain here, so we keep raw units but
    # tell MNE not to assume volts by using a generic scale -- amplitudes
    # in plots will be in the CSV's native units, not calibrated microvolts,
    # unless you already converted to real EEG units when saving (i.e. if
    # this is the *_prc_log.csv path's scaling instead, adjust accordingly).
    stim_data = df["stimulus"].to_numpy().reshape(1, -1)

    ch_names = CHANNEL_NAMES + ["STIM"]
    ch_types = ["eeg"] * 8 + ["stim"]
    info = mne.create_info(ch_names=ch_names, sfreq=fs, ch_types=ch_types)

    all_data = np.vstack([eeg_data, stim_data])
    raw = mne.io.RawArray(all_data, info)

    montage = mne.channels.make_standard_montage("standard_1020")
    raw.set_montage(montage, on_missing="warn")

    return raw


def main():
    parser = argparse.ArgumentParser(description="Plot P300 ERPs around probe/target/irrelevant events")
    parser.add_argument("csv_path", help="Path to the *_eeg_raw_log.csv file (must have a 'stimulus' column)")
    parser.add_argument("--fs", type=float, default=250.0, help="Sampling rate (Hz)")
    parser.add_argument("--tmin", type=float, default=-0.2, help="Epoch start, seconds relative to stimulus")
    parser.add_argument("--tmax", type=float, default=0.8, help="Epoch end, seconds relative to stimulus")
    parser.add_argument("--reject-uv", type=float, default=150.0,
                         help="Peak-to-peak rejection threshold in the CSV's native units "
                              "(default 150 -- adjust based on your data's actual scale, "
                              "see the per-channel stats we've checked in this conversation "
                              "before picking a number blindly)")
    args = parser.parse_args()

    raw = load_csv_as_raw(args.csv_path, fs=args.fs)
    if raw is None:
        print("CSV Not loaded")

    # Preprocessing: same notch + bandpass combo used throughout this project
    raw.notch_filter(freqs=[50], picks="eeg")
    raw.filter(l_freq=1, h_freq=30, picks="eeg")

    events = mne.find_events(raw, stim_channel="STIM")
    if len(events) == 0:
        raise SystemExit(
            "No events found in the 'stimulus' column. Check that the "
            "recording actually has non-zero stimulus codes (i.e. the "
            "marker stream was connected during recording)."
        )

    present_codes = set(events[:, 2])
    event_id_present = {label: code for label, code in EVENT_ID.items() if code in present_codes}
    missing_codes = set(EVENT_ID.values()) - present_codes
    if missing_codes:
        print(f"Note: codes {sorted(missing_codes)} not found in this recording "
              f"(plotting only the conditions actually present: {list(event_id_present)}).")

    epochs = mne.Epochs(
        raw, events, event_id=event_id_present,
        tmin=args.tmin, tmax=args.tmax,
        baseline=(args.tmin, 0),
        reject=dict(eeg=args.reject_uv),
        preload=True,
    )

    print(f"\nEpoch counts per condition (after artifact rejection):")
    for label in event_id_present:
        print(f"  {label}: {len(epochs[label])} epochs")

    evokeds = {label: epochs[label].average() for label in event_id_present}

    # --- Plot 1: Pz waveform, all conditions overlaid (classic P300 channel) ---
    fig1, ax1 = plt.subplots(figsize=(9, 5))
    for label, evoked in evokeds.items():
        pz_idx = evoked.ch_names.index("Pz")
        ax1.plot(evoked.times, evoked.data[pz_idx], label=label,
                 color=CONDITION_COLORS.get(label, None), linewidth=2)
    ax1.axvspan(*P300_WINDOW, color="yellow", alpha=0.15, label="P300 window")
    ax1.axvline(0, color="black", linewidth=0.8, linestyle="--")
    ax1.axhline(0, color="black", linewidth=0.5)
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("Amplitude (native CSV units, NOT calibrated uV)")
    ax1.set_title("Pz: probes vs. target vs. irrelevant")
    ax1.legend()
    fig1.tight_layout()
    fig1.savefig("p300_pz_overlay.png", dpi=150)
    print("Saved p300_pz_overlay.png")

    # --- Plot 2: Cz waveform, same comparison (also a strong P300 site) ---
    fig2, ax2 = plt.subplots(figsize=(9, 5))
    for label, evoked in evokeds.items():
        cz_idx = evoked.ch_names.index("Cz")
        ax2.plot(evoked.times, evoked.data[cz_idx], label=label,
                 color=CONDITION_COLORS.get(label, None), linewidth=2)
    ax2.axvspan(*P300_WINDOW, color="yellow", alpha=0.15, label="P300 window")
    ax2.axvline(0, color="black", linewidth=0.8, linestyle="--")
    ax2.axhline(0, color="black", linewidth=0.5)
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("Amplitude (native CSV units, NOT calibrated uV)")
    ax2.set_title("Cz: probes vs. target vs. irrelevant")
    ax2.legend()
    fig2.tight_layout()
    fig2.savefig("p300_cz_overlay.png", dpi=150)
    print("Saved p300_cz_overlay.png")

    # --- Plot 3: All 8 channels, small multiples, all conditions ---
    fig3, axes = plt.subplots(2, 4, figsize=(16, 7), sharex=True, sharey=True)
    for ax, ch_name in zip(axes.flat, CHANNEL_NAMES):
        for label, evoked in evokeds.items():
            ch_idx = evoked.ch_names.index(ch_name)
            ax.plot(evoked.times, evoked.data[ch_idx],
                     color=CONDITION_COLORS.get(label, None), linewidth=1.5, label=label)
        ax.axvspan(*P300_WINDOW, color="yellow", alpha=0.15)
        ax.axvline(0, color="black", linewidth=0.6, linestyle="--")
        ax.axhline(0, color="black", linewidth=0.4)
        ax.set_title(ch_name)
    axes[0, 0].legend(fontsize=8, loc="upper left")
    fig3.supxlabel("Time (s)")
    fig3.supylabel("Amplitude (native CSV units, NOT calibrated uV)")
    fig3.suptitle("All channels: probes vs. target vs. irrelevant")
    fig3.tight_layout()
    fig3.savefig("p300_all_channels.png", dpi=150)
    print("Saved p300_all_channels.png")

    # --- Mean amplitude in the P300 window, per condition, at Pz ---
    print(f"\nMean Pz amplitude in P300 window {P300_WINDOW[0]}-{P300_WINDOW[1]}s (native CSV units):")
    for label, evoked in evokeds.items():
        pz_idx = evoked.ch_names.index("Pz")
        mask = (evoked.times >= P300_WINDOW[0]) & (evoked.times <= P300_WINDOW[1])
        mean_amp = evoked.data[pz_idx, mask].mean()
        print(f"  {label}: {mean_amp:.2f}")

    plt.show()


if __name__ == "__main__":
    main()