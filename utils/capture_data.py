import numpy as np
from scipy.signal import butter, sosfilt
from pylsl import StreamInlet, resolve_byprop
from collections import deque

def create_butter_bandpass(lowcut, highcut, fs, order=4):
    """
    Designs a Butterworth bandpass filter.
    Using Second-Order Sections (SOS) for numerical stability.
    """
    nyquist = 0.5 * fs
    low = lowcut / nyquist
    high = highcut / nyquist
    # Create the filter coefficients
    sos = butter(order, [low, high], btype='band', output='sos')
    return sos

def live_filtered_stream():
    # 1. Connect to the Unicorn LSL stream
    print("Searching for Unicorn EEG stream...")
    streams = resolve_byprop('type', 'EEG')
    inlet = StreamInlet(streams[0])
    fs = int(inlet.info().nominal_srate()) # Usually 250 Hz
    
    # 2. Build our custom 1-10 Hz filter configuration
    lowcut = 1.0
    highcut = 10.0
    filter_order = 4
    sos_coefficients = create_butter_bandpass(lowcut, highcut, fs, order=filter_order)
    
    # Create a rolling window buffer (e.g., 2 seconds of data to look at patterns)
    max_samples = fs * 2 
    buffer = deque(maxlen=max_samples)
    
    print(f"Filter successfully initialized: {lowcut}-{highcut} Hz")
    print("Streaming live filtered data... Press Ctrl+C to exit.")
    
    try:
        while True:
            sample, timestamp = inlet.pull_sample(timeout=1.0)
            if sample is None:
                print("\nNo Samples, Exiting.")
                break
            else:
                eeg_channels = sample[:8] # Take just the 8 EEG channels
                buffer.append(eeg_channels)
            
                if len(buffer) == max_samples:
                    # Convert buffer to numpy array: shape (n_channels, n_times)
                    raw_window = np.array(buffer).T
                
                    # 3. Apply the 1-10 Hz filter to all 8 channels simultaneously
                    # sosfilt filters along the last axis (time axis) by default
                    filtered_window = sosfilt(sos_coefficients, raw_window)
                
                    # Now 'filtered_window' contains pure 1-10 Hz brain activity!
                    # Let's check the filtered output of Channel 5 (Pz) for P300 spikes
                    pz_filtered_sample = filtered_window[4, -1] 
                
                    if timestamp % 1.0 < 0.04:
                        print(f"Live Cleaned Pz Signal: {pz_filtered_sample:.2f} µV")

    except KeyboardInterrupt:
        print("\nStreaming stopped.")

if __name__ == '__main__':
    # Make sure to run: pip install scipy numpy pylsl
    live_filtered_stream()