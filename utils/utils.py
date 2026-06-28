import os
import threading
import time

# keyboard related imports
from pynput.keyboard import Listener
from pyKey import pressKey, releaseKey

# eeg streaming related imports
from pylsl import StreamInlet, resolve_streams, resolve_byprop


def trigger_jump(delay=0.05):
    """ This function simulates a jump in the game Canabalt """
    trigger_key('space', delay)


def trigger_key(key_name, delay=0.05):
    """ This function simulates a key press """
    pressKey(key_name)
    time.sleep(delay)
    releaseKey(key_name)


class KeyLogger:

    def __init__(self, csv_file_path):

        self.csv_file_path = csv_file_path
        if os.path.exists(csv_file_path):
            raise FileExistsError(f"File {csv_file_path} already exists.")
        self.log_file = open(csv_file_path, 'w', newline='\n')
        self.log_file.write('timestamp,key\n')
        self.log_file.flush()  # Ensure data is written to the file

        self.key_listener = Listener(on_press=self.on_press, on_release=self.on_release)
        self.key_listener.daemon = True

    def start(self):
        """Start the key logger."""
        if not self.key_listener.is_alive():
            self.key_listener.start()

    def on_press(self, key):
        key = str(key)
        key = key.replace("Key.", "")
        print(f"Key pressed: {key}")  # Debug print
        t = time.time()
        self.log_file.write(f"{t},{key}_press\n")
        self.log_file.flush()  # Ensure data is written to the file

    def on_release(self, key):
        key = str(key)
        key = key.replace("'", "")
        key = key.replace("Key.", "")
        print(f"Key released: {key}")  # Debug print
        t = time.time()
        self.log_file.write(f"{t},{key}_release\n")
        self.log_file.flush()  # Ensure data is written to the file

    def __del__(self):
        self.key_listener.stop()
        self.log_file.close()


def get_lsl_stream(stream_name) -> StreamInlet:
    """
    Get an LSL stream with a specific name.

    Parameters:
        stream_name (str): The name of the LSL stream to find.
    """
    print(f"Looking for an LSL stream with name '{stream_name}'...")
    streams = resolve_streams()

    print("available stream names:")
    print([stream.name() for stream in streams])

    # Iterate over all streams to find a stream with a matching name
    for i, stream in enumerate(streams):
        if stream.name() == stream_name:
            inlet = StreamInlet(streams[i])
            return inlet

    print(f"Stream '{stream_name}' not found.")
    return None


class EEGListener:

    """ This class acts as a listener for EEG data runnning in the background.
    A callback function can be given to process the data as it arrives.
    The main part of this class is to handle the threading and the LSL stream.
    """

    def __init__(self, stream_name, callback=None):
        self.stream_name = stream_name
        self.callback = callback

        # Resolve the LSL stream
        self.lsl_stream = get_lsl_stream(stream_name)
        if self.lsl_stream is None:
            raise ValueError(f"Stream '{stream_name}' not found.")

        # Create a new thread for the LSL stream
        self.running = False
        self.thread = threading.Thread(target=self.record_eeg)
        self.thread.daemon = True

    def record_eeg(self):
        """Record EEG data from the LSL stream."""
        self.running = True
        while self.running:
            sample, eeg_time = self.lsl_stream.pull_sample(timeout=1.0)  # blocking
            sys_time = time.time()

            if sample is None:  # timeout
                print("No sample received.")  # Debug print
                continue

            # print(f"Sample received: {sample}")  # Debug print
            if self.callback:
                self.callback(sample, sys_time, eeg_time)

    def start(self):
        """Start the EEG listener."""
        if not self.thread.is_alive():
            self.thread.start()

    def stop(self):
        """Stop the EEG listener."""
        if self.thread.is_alive():
            self.running = False
            self.thread.join(timeout=1)
            if self.thread.is_alive():
                print("Warning: Thread did not stop in time.")

    def close(self):
        """Close the EEG listener."""
        self.stop()
        if self.lsl_stream:
            self.lsl_stream.close_stream()
            self.lsl_stream = None

    def __del__(self):
        """Destructor for the EEG listener."""
        self.close()


class MarkerListener:
    """
    Listens to a Markers-type LSL stream (e.g. the one created by
    cit_image_presentation.py) in a background thread, and keeps track of the
    single most recent marker code + its LSL timestamp. EEGLogger polls
    `get_latest_marker_code(eeg_timestamp)` once per incoming EEG sample to
    decide what (if anything) to write in its stimulus column for that row.
    """

    def __init__(self, stream_name="CIT_Markers", timeout=10):
        print(f"Looking for marker stream '{stream_name}'...")
        streams = resolve_byprop("name", stream_name, timeout=timeout)
        if not streams:
            raise ValueError(
                f"Marker stream '{stream_name}' not found. Make sure your "
                f"stimulus presentation script (e.g. cit_image_presentation.py) "
                f"is already running before starting the EEG logger."
            )
        self.inlet = StreamInlet(streams[0])
        print(f"Connected to marker stream '{stream_name}'.")

        self._lock = threading.Lock()
        self._pending = []  # list of (event_code, marker_timestamp), oldest first
        self.running = False
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)

    def start(self):
        if not self.thread.is_alive():
            self.running = True
            self.thread.start()

    def _listen_loop(self):
        while self.running:
            sample, timestamp = self.inlet.pull_sample(timeout=1.0)
            if sample is None:
                continue
            with self._lock:
                self._pending.append((int(sample[0]), timestamp))

    def consume_marker_for(self, eeg_timestamp):
        """
        Returns the event code that should be attached to an EEG sample at
        eeg_timestamp, or 0 if no marker applies yet. Pops (consumes) the
        oldest pending marker once an EEG sample at or after its timestamp
        arrives, so each marker gets attached exactly once.
        """
        with self._lock:
            if self._pending and self._pending[0][1] <= eeg_timestamp:
                code, _ = self._pending.pop(0)
                return code
        return 0

    def stop(self):
        if self.thread.is_alive():
            self.running = False
            self.thread.join(timeout=1)

    def close(self):
        self.stop()
        if self.inlet:
            self.inlet.close_stream()
            self.inlet = None

    def __del__(self):
        self.close()


class EEGLogger:

    def __init__(self, log_file_path, stream_name="UnicornRecorderLSLStream",
                 marker_stream_name=None):
        """
        marker_stream_name: if given (e.g. "CIT_Markers"), this logger will
        ALSO connect to that LSL marker stream and add a 'stimulus' column to
        the CSV, populated with the event code active at each EEG sample (0
        if no marker at that moment). Leave as None (default) to log EEG only,
        with no behavior change from before.
        """
        self.stream_name = stream_name
        self.log_file_path = log_file_path
        self.use_markers = marker_stream_name is not None

        self.log_file = open(log_file_path, 'w', newline='\n')
        if self.use_markers:
            self.log_file.write('sys_time,eeg_time,ch1,ch2,ch3,ch4,ch5,ch6,ch7,ch8,stimulus\n')
        else:
            self.log_file.write('sys_time,eeg_time,ch1,ch2,ch3,ch4,ch5,ch6,ch7,ch8\n')
        self.log_file.flush()  # Ensure data is written to the file

        self.marker_listener = None
        if self.use_markers:
            self.marker_listener = MarkerListener(stream_name=marker_stream_name)
            self.marker_listener.start()

        self.eeg_listener = EEGListener(stream_name, self.log_eeg_data)

    def start(self):
        """Start the EEG logger."""
        if not self.eeg_listener.thread.is_alive():
            self.eeg_listener.start()

    def log_eeg_data(self, sample, sys_time, eeg_time):
        """Log EEG data (and, if enabled, the current stimulus marker code) to a CSV file."""
        sample = sample[:8]  # remove non-channel data
        if self.use_markers:
            stim_code = self.marker_listener.consume_marker_for(eeg_time)
            self.log_file.write(f"{sys_time},{eeg_time},{','.join(map(str, sample))},{stim_code}\n")
        else:
            self.log_file.write(f"{sys_time},{eeg_time},{','.join(map(str, sample))}\n")
        self.log_file.flush()  # Ensure data is written to the file

    def __del__(self):
        """Destructor for the EEG logger."""
        self.eeg_listener.stop()
        if self.marker_listener is not None:
            self.marker_listener.stop()
        self.log_file.close()