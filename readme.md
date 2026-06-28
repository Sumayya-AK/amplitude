# EEG Hackathon 🧠🎮

Hey hackers! 👋

Welcome to the EEG Hackathon repository! You've come to the right place to dive into EEG data analysis in a fun and engaging way.
In this repository, you'll find all the tools you need to collect and analyze EEG data while playing the game "Canabalt."

The goal of this project is to process EEG data to detect when a player presses a key and classify the keystroke based on a short signal window. Let’s get started!

## 🚀 Getting Started

### General System Requirements ⚙️

Before you begin, ensure your system meets the following requirements:

- Operating System: Windows 10 or later
- Hardware: Bluetooth capability (to connect to the EEG cap)
- Python Environment: Anaconda (recommended) or an alternative virtual environment manager

### Install the EEG Software 🖥️

Each team has been provided with a Unicorn Hybrid Black EEG cap from g.tec. This wireless, user-friendly EEG cap will be used for data collection.

To set it up:

1. Download the Unicorn Suite software from the g.tec website.
1. Install the software and launch it.
1. Navigate to the "My Unicorn" tab and connect to your EEG cap:
    - Ensure the EEG cap is fully charged and powered on.
    - Check your Bluetooth settings to confirm that your PC is paired with the cap.
1. Once connected, go to the "Apps" tab in Unicorn Suite and download Unicorn Recorder.
    - Optionally, you can also install Unicorn Bandpower for testing purposes.

### Install Python Libraries 🐍

We’ll use [MNE-Python](https://mne.tools/stable/index.html), a powerful library for processing and analyzing EEG data.

Follow these steps to set up your Python environment:

- Ensure you have [Anaconda](https://www.anaconda.com/docs/getting-started/miniconda/install#power-shell) installed on your system.
- Run the following commands in your terminal or PowerShell:

```bash
conda create -n eeg python=3.13 -y
conda activate eeg
pip install -r requirements.txt
This will create a virtual environment named eeg and install all required dependencies listed in requirements.txt.
```


## Data Collection 📊

To collect EEG data while playing the game, follow these steps:

1. Set up the EEG cap:
    - Ensure the cap is properly fitted and all electrodes are in contact with your scalp.
    - Turn the cap on.

1. Launch the Unicorn Suite software and connect to your EEG cap.

1. Select the filter settings in the Unicorn Suite - this is a recommendation:
    - Use a bandpass filter between 0.1 Hz and 50 Hz.
    - Use a notch filter at 50 Hz to remove power line noise.
    - use the OSCAR filter if you want to remove eye blinks and muscle artifacts.

1. Run the `cit_server.py` script to start collecting the EEG data and analyse the data


1. After you finish playing the game, stop the data collection script by pressing `Ctrl + C` in the terminal.

## Data Analysis 🔍

Once you have collected the EEG data, you can analyze it using the analysis tab. 
This includes the following steps:

1. Load the EEG data 
2. Preprocess the data (e.g., filtering, epoching).
3. Visualize the results.


## EEG LIE DETECTION

Lie can be detected based on the ERP signals, especially P300. CIT test is used to identify weather the suspect is lying.
