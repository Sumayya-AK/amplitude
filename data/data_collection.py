import os
import time

from utils.utils import KeyLogger, EEGLogger


def get_subject_id():
    """Prompt the user for a subject ID and validate it."""
    subject_id = input("Enter the subject ID:\n")
    assert subject_id.isdigit(), "Subject ID must be a number."
    subject_id = int(subject_id)
    assert 0 < subject_id < 100, "Subject ID must be a two-digit number."
    return subject_id


def main():

    # get the file paths for the new recording 
    #key_log_dir = "data/key_recordings"
    eeg_log_dir = "data/eeg_recordings"
    eeg_raw_log_dir = "data/eeg_raw_recordings"

    # make sure path is valid
    #assert os.path.exists(key_log_dir), f"Key log directory {key_log_dir} does not exist."
    assert os.path.exists(eeg_log_dir), f"EEG log directory {eeg_log_dir} does not exist."
    assert os.path.exists(eeg_raw_log_dir), f"EEG raw log directory {eeg_raw_log_dir} does not exist."

    # get the subject ID for this run
    subject_id = get_subject_id()
    #key_log_dir = os.path.join(key_log_dir, f"sub-{subject_id:02d}")
    eeg_log_dir = os.path.join(eeg_log_dir, f"sub-{subject_id:02d}")
    eeg_raw_log_dir = os.path.join(eeg_raw_log_dir, f"sub-{subject_id:02d}")
    #os.makedirs(key_log_dir, exist_ok=True)
    os.makedirs(eeg_log_dir, exist_ok=True)
    os.makedirs(eeg_raw_log_dir, exist_ok=True)

    # get the run number for this recording
    run_num = len([f for f in os.listdir(eeg_log_dir) if f.endswith(".csv")]) + 1
    recording_name = f"sub-{subject_id:02d}_run-{run_num:03d}"
    #key_log_path = os.path.join(key_log_dir, f"{recording_name}_key_log.csv")
    eeg_prc_log_path = os.path.join(eeg_log_dir, f"{recording_name}_eeg_prc_log.csv")
    eeg_raw_log_path = os.path.join(eeg_raw_log_dir, f"{recording_name}_eeg_raw_log.csv")

    # avoid overwriting existing files
    #assert not os.path.exists(key_log_path), f"Key log file {key_log_path} already exists."
    assert not os.path.exists(eeg_prc_log_path), f"EEG log file {eeg_prc_log_path} already exists."
    assert not os.path.exists(eeg_raw_log_path), f"EEG raw log file {eeg_raw_log_path} already exists."


    # Initialize & start loggers
    #key_logger = KeyLogger(key_log_path)
    eeg_prc_logger = EEGLogger(eeg_prc_log_path, stream_name="UnicornRecorderLSLStream")
    eeg_raw_logger = EEGLogger(eeg_raw_log_path, stream_name="UnicornRecorderRawDataLSLStream")
    #key_logger.start()
    eeg_prc_logger.start()
    eeg_raw_logger.start()
    

    # Keep the script running to log data
    try:
        while True:
            time.sleep(3)
            print("Logging data...")

    except KeyboardInterrupt:
        print("Stopping data collection...")
        #del key_logger
        del eeg_prc_logger
        del eeg_raw_logger



if __name__ == "__main__":
    main()