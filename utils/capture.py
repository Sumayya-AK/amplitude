import csv
import time
from collections import deque

import numpy as np
from pylsl import StreamInlet, resolve_byprop
from scipy.signal import butter, sosfilt


def create_butter_bandpass(lowcut, highcut, fs, order=4):
    """
    Designs a Butterworth bandpass filter.
    Using Second-Order Sections (SOS) for numerical stability.
    """
    nyquist = 0.5 * fs
    low = lowcut / nyquist
    high = highcut / nyquist
    sos = butter(order, [low, high], btype='band', output='sos')
    return sos


def live_filtered_stream(output_csv="unicorn_recording.csv", n_channels=8):
    # 1. Connect to the Unicorn LSL stream
    print("Searching for Unicorn EEG stream...")
    streams = resolve_byprop('type', 'EEG')
    if not streams:
        print("No EEG stream found. Is Unicorn Suite / the LSL app running and streaming?")
        return

    inlet = StreamInlet(streams[0])
    fs = int(inlet.info().nominal_srate())  # Usually 250 Hz
    print(f"Connected. Sampling rate reported as {fs} Hz.")

    # 2. Build our custom 1-10 Hz filter configuration
    lowcut = 8.0
    highcut = 12.0
    filter_order = 4
    sos_coefficients = create_butter_bandpass(lowcut, highcut, fs, order=filter_order)

    # Maintain filter state across calls so we filter continuously instead of
    # restarting (and getting a transient) on every chunk.
    # zi shape: (n_sections, n_channels, 2) when filtering along axis=-1 with
    # multiple independent channels stacked on axis 0.
    n_sections = sos_coefficients.shape[0]
    zi = np.zeros((n_sections, n_channels, 2))

    # Rolling window buffer just for live display purposes (e.g. 2 seconds)
    max_samples = fs * 2
    buffer = deque(maxlen=max_samples)

    print(f"Filter successfully initialized: {lowcut}-{highcut} Hz")
    print(f"Streaming live filtered data and saving to '{output_csv}'.")
    print("Press Ctrl+C to stop recording.")

    header = (
        [f"EEG{i+1}_raw" for i in range(n_channels)]
        + [f"EEG{i+1}_filtered" for i in range(n_channels)]
        + ["lsl_timestamp"]
    )

    csv_file = open(output_csv, "w", newline="")
    writer = csv.writer(csv_file)
    writer.writerow(header)

    consecutive_timeouts = 0
    max_consecutive_timeouts = 5  # tolerate brief hiccups before giving up

    try:
        while True:
            sample, timestamp = inlet.pull_sample(timeout=1.0)

            if sample is None:
                consecutive_timeouts += 1
                print(f"\nNo sample received (timeout {consecutive_timeouts}/{max_consecutive_timeouts}).")
                if consecutive_timeouts >= max_consecutive_timeouts:
                    print("Stream appears to have stopped. Exiting.")
                    break
                continue

            consecutive_timeouts = 0  # reset on a successful pull

            eeg_channels = np.array(sample[:n_channels], dtype=float)
            buffer.append(eeg_channels)

            # 3. Apply the 1-10 Hz filter to this single new sample, carrying
            # the filter state forward so the output is continuous across
            # the whole recording (no per-chunk edge transients).
            sample_in = eeg_channels.reshape(n_channels, 1)  # shape (channels, 1 timepoint)
            filtered_sample, zi = sosfilt(sos_coefficients, sample_in, axis=-1, zi=zi)
            filtered_values = filtered_sample[:, 0]

            # 4. Write raw + filtered values for this sample to CSV
            row = list(eeg_channels) + list(filtered_values) + [timestamp]
            writer.writerow(row)

            # Flush to disk roughly once a second so a crash/kill doesn't lose
            # more than ~1s of buffered-but-unwritten data.
            if len(buffer) % fs == 0:
                csv_file.flush()

            # Occasional live printout (~once per second) of filtered Pz (Ch5)
            pz_filtered_sample = filtered_values[4]
            if timestamp % 1.0 < 0.004 * fs / 250:  # roughly once per second regardless of fs
                print(f"Live Cleaned Pz Signal: {pz_filtered_sample:.2f} µV")

    except KeyboardInterrupt:
        print("\nStreaming stopped by user.")
    finally:
        csv_file.close()
        print(f"Recording saved to '{output_csv}'.")


if __name__ == '__main__':
    # Make sure to run: pip install scipy numpy pylsl
    live_filtered_stream(output_csv="unicorn_recording.csv")