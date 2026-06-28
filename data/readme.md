# Data Folder

The data folder is intended to contain all the data recordings from the data colection as well as the processed data and datasets for visualization and training. 

The data folder is organized as follows:

- datasets: This folder contains the combined data of eeg signals and key strokes.
- eeg_raw_recordings: This folder contains the raw data recordings of the EEG signals.
- eeg_recordings: This folder contains the recordings of the EEG signals processed based on the selection in the g.tec Recorder.
- key_strokes_recordings: This folder contains the raw data recordings of the key strokes.
- data_collection.py: This file needs to be run to collect the eeg and key stroke data.
- combine_data.py: This file needs to be run to combine the eeg and key stroke data into a single dataset.
- event_ids.json: This file is used to filter the relevant key stroke events and map them to unique event ids.  
