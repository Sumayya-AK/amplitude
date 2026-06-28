"""
SSVEP (Steady-State Visual Evoked Potential) analysis for Unicorn 8-channel EEG recordings.

How SSVEP works:
  You flicker a visual stimulus (light, screen pattern) at a fixed frequency,
  e.g. 10 Hz. The visual cortex entrains to that rate, so the EEG power
  spectrum should show a clear peak at exactly that frequency (and often at
  2x, 3x harmonics too), strongest over occipital/posterior channels.

  Unlike P300, this does NOT require trial-by-trial trigger markers -- you
  just need to know which time window the flicker was running, and look at
  the power spectrum during that window.

Usage:
    python ssvep_analysis.py unicorn_recording.csv --flicker-freq 10
    python ssvep_analysis.py unicorn_recording.csv --flicker-freq 10 --start 5 --end 35
"""

import argparse

import numpy as np
import pandas as pd
from scipy.signal import welch, butter, sosfiltfilt


def bandpass_filter(data, fs, lowcut=1.0, highcut=40.0, order=4):
    """Zero-phase bandpass filter applied offline (safe to use sosfiltfilt
    here since this is a saved file, not a live stream)."""
    nyq = fs / 2
    sos = butter(order, [lowcut / nyq, highcut / nyq], btype="band", output="sos")
    return sosfiltfilt(sos, data, axis=0)


def compute_snr_spectrum(freqs, pxx, target_freq, n_neighbor_bins=10, n_exclude_bins=1):
    """
    SNR at target_freq = power at that frequency / average power in nearby
    'noise' bins (excluding the target bin itself and its immediate neighbors).
    This is the standard way to quantify SSVEP strength.
    """
    idx_target = np.argmin(np.abs(freqs - target_freq))
    lo = max(0, idx_target - n_neighbor_bins)
    hi = min(len(freqs), idx_target + n_neighbor_bins + 1)

    neighbor_idx = list(range(lo, hi))
    exclude_idx = list(range(idx_target - n_exclude_bins, idx_target + n_exclude_bins + 1))
    noise_idx = [i for i in neighbor_idx if i not in exclude_idx]

    signal_power = pxx[idx_target]
    noise_power = np.mean(pxx[noise_idx]) if noise_idx else np.nan
    snr = signal_power / noise_power if noise_power and noise_power > 0 else np.nan
    return signal_power, noise_power, snr


def main():
    parser = argparse.ArgumentParser(description="SSVEP analysis for Unicorn EEG CSV recordings")
    parser.add_argument("csv_path", help="Path to the recording CSV")
    parser.add_argument("--flicker-freq", type=float, required=True,
                         help="The frequency (Hz) you flickered the visual stimulus at")
    parser.add_argument("--fs", type=float, default=250.0,
                         help="Sampling rate in Hz (Unicorn default is 250)")
    parser.add_argument("--start", type=float, default=None,
                         help="Start time (s) of the flicker window, relative to recording start")
    parser.add_argument("--end", type=float, default=None,
                         help="End time (s) of the flicker window, relative to recording start")
    parser.add_argument("--n-harmonics", type=int, default=3,
                         help="How many harmonics of the flicker frequency to check (default 3)")
    parser.add_argument("--use-filtered-cols", action="store_true",
                         help="Use the *_filtered columns instead of *_raw")
    args = parser.parse_args()

    df = pd.read_csv(args.csv_path)

    n_channels = 8
    suffix = "_filtered" if args.use_filtered_cols else "_raw"
    chan_cols = [f"EEG{i}_{('filtered' if args.use_filtered_cols else 'raw')}" for i in range(1, n_channels + 1)]
    missing = [c for c in chan_cols if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing expected columns: {missing}. Found columns: {df.columns.tolist()}")

    data = df[chan_cols].to_numpy()  # shape (n_samples, 8)
    fs = args.fs

    # Use the recording's own timestamp column if present, to slice the
    # requested flicker window. Falls back to sample-index timing otherwise.
    if "lsl_timestamp" in df.columns:
        t = df["lsl_timestamp"].to_numpy()
        t = t - t[0]
    else:
        t = np.arange(len(df)) / fs

    start = args.start if args.start is not None else t[0]
    end = args.end if args.end is not None else t[-1]
    mask = (t >= start) & (t <= end)
    window_data = data[mask]
    n_window = window_data.shape[0]

    if n_window < fs * 2:
        print(f"Warning: only {n_window} samples ({n_window/fs:.1f}s) in the selected window. "
              f"SSVEP frequency resolution improves with longer windows (aim for >=4-8s).")

    print(f"Analyzing window: {start:.2f}s to {end:.2f}s ({n_window} samples, ~{n_window/fs:.1f}s)")
    print(f"Target flicker frequency: {args.flicker_freq} Hz (and {args.n_harmonics - 1} harmonic(s))")
    print()

    # Light bandpass to remove slow drift and very high-frequency noise before
    # computing the spectrum. Keep the band wide enough to include the
    # flicker frequency and its harmonics.
    max_harmonic_freq = args.flicker_freq * args.n_harmonics
    highcut = min(45.0, max_harmonic_freq + 5.0)
    filtered_window = bandpass_filter(window_data, fs, lowcut=1.0, highcut=highcut)

    nperseg = min(int(fs * 4), n_window)  # 4-second segments for decent frequency resolution
    if nperseg < 8:
        nperseg = n_window

    channel_names = [f"Ch{i}" for i in range(1, n_channels + 1)]
    results = []

    for ch_idx, ch_name in enumerate(channel_names):
        sig = filtered_window[:, ch_idx]
        freqs, pxx = welch(sig, fs=fs, nperseg=nperseg)

        harmonics_info = []
        for h in range(1, args.n_harmonics + 1):
            target = args.flicker_freq * h
            if target > freqs[-1]:
                continue
            signal_power, noise_power, snr = compute_snr_spectrum(freqs, pxx, target)
            harmonics_info.append((h, target, signal_power, snr))

        results.append((ch_name, harmonics_info))

    # Print a summary table: SNR at fundamental frequency per channel
    print("SSVEP SNR at fundamental frequency (signal power / nearby noise floor):")
    print(f"{'Channel':<10}{'Freq (Hz)':<12}{'SNR':<10}{'Verdict'}")
    snr_fundamental = {}
    for ch_name, harmonics_info in results:
        if not harmonics_info:
            continue
        h, target, signal_power, snr = harmonics_info[0]
        snr_fundamental[ch_name] = snr
        verdict = "likely SSVEP" if snr is not None and snr >= 3 else ("weak/borderline" if snr is not None and snr >= 1.5 else "no clear response")
        print(f"{ch_name:<10}{target:<12.2f}{snr:<10.2f}{verdict}")

    print()
    best_channel = max(snr_fundamental, key=snr_fundamental.get) if snr_fundamental else None
    if best_channel:
        print(f"Strongest SSVEP response: {best_channel} (SNR={snr_fundamental[best_channel]:.2f})")
        print("Note: occipital/posterior channels typically show the strongest SSVEP since "
              "they sit over visual cortex. Check your electrode layout to confirm which "
              "physical position each channel number corresponds to.")

    print()
    print("Full harmonic breakdown per channel:")
    for ch_name, harmonics_info in results:
        print(f"  {ch_name}:")
        for h, target, signal_power, snr in harmonics_info:
            print(f"    {h}x harmonic ({target:.2f} Hz): power={signal_power:.4f}, SNR={snr:.2f}")

    # Save the spectra to a CSV for further plotting/inspection if desired
    out_rows = []
    for ch_idx, ch_name in enumerate(channel_names):
        sig = filtered_window[:, ch_idx]
        freqs, pxx = welch(sig, fs=fs, nperseg=nperseg)
        for f_val, p_val in zip(freqs, pxx):
            out_rows.append({"channel": ch_name, "frequency_hz": f_val, "power": p_val})

    spectrum_df = pd.DataFrame(out_rows)
    out_path = "ssvep_spectrum_output.csv"
    spectrum_df.to_csv(out_path, index=False)
    print(f"\nFull power spectra saved to '{out_path}' (columns: channel, frequency_hz, power)")


if __name__ == "__main__":
    main()