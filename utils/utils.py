import os
import threading
import time

# keyboard related imports
from pynput.keyboard import Listener
from pyKey import pressKey, releaseKey

# eeg streaming related imports
from pylsl import StreamInlet, resolve_streams


def trigger_jump(delay=0.05):
    """ This function simulates a jump in the game Canabalt """
    trigger_key('space', delay)


def trigger_key(key_name, delay=0.05):
    """ This function simulates a key press """
    pressKey(key_name)
    time.sleep(delay)
    releaseKey(key_name)


## Fallback Method: Direct Win32 API (For Resistant Games)
# import ctypes

# # Key codes: https://learn.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes
# SPACE_KEY = 0x20

# def send_key():
#     ctypes.windll.user32.SendInput(
#         1,
#         ctypes.byref(ctypes.c_ulong(0)),  # MOUSEINPUT dummy
#         ctypes.sizeof(ctypes.c_ulong(0))
#     )
#     # Space key press/release
#     ctypes.windll.user32.keybd_event(SPACE_KEY, 0, 0, 0)  # Press
#     ctypes.windll.user32.keybd_event(SPACE_KEY, 0, 2, 0)  # Release


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

    def __init__(self, stream_name, marker_stream_name = "CIT_Markers", callback=None):
        self.stream_name = stream_name
        self.callback = callback

        # Resolve the LSL stream
        self.lsl_stream = get_lsl_stream(stream_name)
        if self.lsl_stream is None:
            raise ValueError(f"Stream '{stream_name}' not found.")
        
        # Create a new thread for the LSL stream
        self.running= False
        self.thread = threading.Thread(target=self.record_eeg)
        self.thread.daemon = True

    def record_eeg(self):
        """Record EEG data from the LSL stream."""
        self.running = True
        while self.running:
            sample, eeg_time = self.lsl_stream.pull_sample(timeout=1.0) # blocking
            sys_time = time.time()
            
            if sample is None: # timeout
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
    

class EEGLogger:

    def __init__(self, log_file_path, stream_name="UnicornRecorderLSLStream", marker_stream_name ="CIT_Markers"):
        self.stream_name = stream_name
        self.log_file_path = log_file_path

        self.log_file = open(log_file_path, 'w', newline='\n')
        self.log_file.write('sys_time,eeg_time,ch1,ch2,ch3,ch4,ch5,ch6,ch7,ch8\n')
        self.log_file.flush()  # Ensure data is written to the file

        self.eeg_listener = EEGListener(stream_name, self.log_eeg_data)
    
    def start(self):
        """Start the EEG logger."""
        if not self.eeg_listener.thread.is_alive():
            self.eeg_listener.start()

    def log_eeg_data(self, sample, sys_time, eeg_time):
        """Log EEG data to a CSV file."""
        sample = sample[:8]  # remove non-channel data
        self.log_file.write(f"{sys_time},{eeg_time},{','.join(map(str, sample))}\n")
        self.log_file.flush()  # Ensure data is written to the file

    def __del__(self):
        """Destructor for the EEG logger."""
        self.eeg_listener.stop()
        self.log_file.close()

