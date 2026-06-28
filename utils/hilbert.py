"""
Standalone CSV recorder for the Unicorn LSL stream.

This is fully independent from capture.py -- it does not modify or require
changes to that script. It opens its own connection to the same LSL stream
(multiple inlets can subscribe to one LSL stream at once, so this is safe to
run alongside capture.py if you want the live console view at the same time),
and simply saves the raw 8-channel EEG samples to a CSV file.

That CSV is what hilbert_envelope.py reads afterward.

Usage:
    python record_to_csv.py
    python record_to_csv.py --output my_recording.csv --duration 60
"""

import argparse
import csv
import time

import numpy as np
from pylsl import StreamInlet, resolve_byprop


def record_to_csv(output_csv="unicorn_recording.csv", n_channels=8, duration=None):
    print("Searching for Unicorn EEG stream...")
    streams = resolve_byprop('type', 'EEG')
    if not streams:
        print("No EEG stream found. Is Unicorn Suite / the LSL app running and streaming?")
        return

    inlet = StreamInlet(streams[0])
    fs = int(inlet.info().nominal_srate())
    print(f"Connected. Sampling rate reported as {fs} Hz.")

    header = [f"EEG{i+1}_raw" for i in range(n_channels)] + ["lsl_timestamp"]

    csv_file = open(output_csv, "w", newline="")
    writer = csv.writer(csv_file)
    writer.writerow(header)

    print(f"Recording to '{output_csv}'.")
    if duration:
        print(f"Will stop automatically after {duration} seconds.")
    print("Press Ctrl+C to stop recording early.")

    consecutive_timeouts = 0
    max_consecutive_timeouts = 5
    n_samples = 0
    start_time = time.time()

    try:
        while True:
            if duration and (time.time() - start_time) >= duration:
                print(f"\nReached {duration}s duration limit.")
                break

            sample, timestamp = inlet.pull_sample(timeout=1.0)

            if sample is None:
                consecutive_timeouts += 1
                print(f"\nNo sample received (timeout {consecutive_timeouts}/{max_consecutive_timeouts}).")
                if consecutive_timeouts >= max_consecutive_timeouts:
                    print("Stream appears to have stopped. Exiting.")
                    break
                continue

            consecutive_timeouts = 0

            eeg_channels = sample[:n_channels]
            writer.writerow(list(eeg_channels) + [timestamp])
            n_samples += 1

            if n_samples % fs == 0:  # roughly once a second
                csv_file.flush()

    except KeyboardInterrupt:
        print("\nRecording stopped by user.")
    finally:
        csv_file.close()
        elapsed = time.time() - start_time
        print(f"Saved {n_samples} samples (~{elapsed:.1f}s) to '{output_csv}'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record Unicorn LSL stream to CSV")
    parser.add_argument("--output", default="unicorn_recording.csv", help="Output CSV path")
    parser.add_argument("--duration", type=float, default=None,
                         help="Recording duration in seconds (default: run until Ctrl+C)")
    args = parser.parse_args()

    # Make sure to run: pip install numpy pylsl
    record_to_csv(output_csv=args.output, duration=args.duration)