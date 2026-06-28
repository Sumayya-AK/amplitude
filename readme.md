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

### Download the Game 🎮
For this hackathon, we’ll use "Canabalt" a classic endless runner game where players jump over obstacles by pressing the space bar. This setup provides us with clean, well-defined stimulus onset events (space bar presses) for EEG data collection.

We’ve also included an alternative game, "2048" which offers a more relaxed gameplay experience but involves more complex controls.

To get started with _Canabalt_:

1. Clone or download the open-source repository from GitHub: [Canabalt GitHub Repo](https://github.com/ninjamuffin99/canabalt-hf).
1. Follow the instructions in the repository to compile the game for Windows. \
    If you encounter issues compiling it for Windows:
    - Try compiling it for HTML5 instead.
    - You’ll need [Node.js](https://nodejs.org/en/download) installed on your system to run it in your browser.

Let us know if you encounter any issues or have questions during setup — happy hacking! 🚀


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

1. Run the `data_collection.py` script to start collecting the EEG data and the key logger

```bash
# run from the root of the repository
python -m data.data_collection
```

1. After you finish playing the game, stop the data collection script by pressing `Ctrl + C` in the terminal.

After collecting the data you can run the `combine_data.py` script in the data folder to merge the logged key presses with the EEG data. Make sure the that the `event_ids` json file maps all the key events you are interessted in (should only include space bra pressed for Canabalt).

## Data Analysis 🔍

Once you have collected the EEG data, you can analyze it using the provided notebook `signal_analysis.ipynb`. 
This notebook includes the following steps:

1. Load the EEG data and the key press events.
1. Preprocess the data (e.g., filtering, epoching).
1. Visualize the results.

## Training a Classifier 🏋️

There is a folder called `features` to define the feature extraction methods and a class to build the final feature extractor. \
The model machine learning models and deep learning architectures should be stored in the `models` folder. \
To train a classifier, you can use the provided scripts in the `train` folder.

## EEG Control 🧠

To control the game using EEG signals you can use the `eeg_keyboard.py` script in the utils folder. Add your trained model from the `checkpoints` folder to the script and run it. Depending on your setup you have to change what data is given to the model.
