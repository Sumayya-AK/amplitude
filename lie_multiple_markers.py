"""
P300 Concealed Information Test using IMAGES, with pygame for display.

How it works:
  - You put your image files in an `images/` folder next to this script
  - One or more images are "probes" -- things your friend recognizes
  - One image is the "target" -- a known image they're told to react to
    (e.g. press spacebar when they see it) -- this is the positive control
  - The rest are "irrelevant" images -- neutral, shown more often than the
    probe/target so the sequence looks like a normal oddball stream

Each time an image is displayed on screen, an LSL marker is sent in the SAME
moment, so the marker timestamp matches when your friend actually saw it.
Each probe image gets its own unique marker code (see PROBE_EVENT_CODES),
so you can distinguish exactly which probe was shown afterward.

Folder layout expected:
    your_project_folder/
    ├── cit_image_presentation.py   <- this file
    └── images/
        ├── probe.jpg                <- recognized image
        ├── probe1.jpg                <- another recognized image
        ├── probe2.jpg                <- another recognized image
        ├── target.jpg                <- known/respond-to image
        ├── irrelevant_1.jpg
        ├── irrelevant_2.jpg
        └── ... (as many irrelevants as you like)

Usage:
    python cit_image_presentation.py
"""

import os
import random
import time

import pygame
from pylsl import StreamInfo, StreamOutlet

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.path.join(SCRIPT_DIR, "images")
PROBE_FILENAMES = {"probe1.JPG", "probe2.JPG", "probe3.JPG"}  # all images your friend recognizes
TARGET_FILENAME = "target.jpg"      # known image they respond to (positive control)
# Everything else in IMAGE_DIR (besides probes/target) is treated as irrelevant.
# Each probe image gets its OWN marker code (see PROBE_EVENT_CODES below), so
# you can tell exactly which probe was shown at analysis time, rather than
# pooling them all under one generic "probe" code.

N_IRRELEVANT_PER_BLOCK = 5   # irrelevant images shown between each probe/target
N_BLOCKS = 15                # repeats of the irrelevant+probe+target cycle
IMAGE_DURATION_S = 1.0       # how long each image stays on screen
ISI_S = 1.5                  # blank gray screen between images

# Fixed codes for the non-probe trial types.
EVENT_CODES = {
    "irrelevant": 1,
    "target": 3,
    "response": 4,
}

# Each probe filename gets its own unique code, starting at 100 so there's no
# risk of colliding with the fixed codes above (or with each other, even if
# you add more probes later). Sorted so the same filename always gets the
# same code across different runs of the script.
#   e.g. {"probe.jpg": 100, "probe1.jpg": 101, "probe2.jpg": 102}
PROBE_EVENT_CODES = {
    filename: 100 + i for i, filename in enumerate(sorted(PROBE_FILENAMES))
}

SCREEN_SIZE = (800, 600)
BACKGROUND_COLOR = (40, 40, 40)


def create_marker_outlet(stream_name="CIT_Markers"):
    info = StreamInfo(
        name=stream_name,
        type="Markers",
        channel_count=1,
        nominal_srate=0,
        channel_format="int32",
        source_id="cit_image_marker_stream",
    )
    outlet = StreamOutlet(info)
    print(f"Marker LSL outlet '{stream_name}' created and broadcasting.")
    return outlet


def send_marker(outlet, event_code):
    outlet.push_sample([event_code])


def discover_images(image_dir):
    """
    Scans the images/ folder and sorts files into probes, target, and
    irrelevant categories based on filename.
    """
    if not os.path.isdir(image_dir):
        raise FileNotFoundError(
            f"Image folder '{image_dir}' not found. Create it next to this "
            f"script and put your images inside (see the docstring at the "
            f"top of this file for the expected layout)."
        )

    all_files = [
        f for f in os.listdir(image_dir)
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp"))
    ]

    missing_probes = PROBE_FILENAMES - set(all_files)
    if missing_probes:
        raise FileNotFoundError(
            f"Expected probe image(s) {sorted(missing_probes)} not found in '{image_dir}'."
        )
    if TARGET_FILENAME not in all_files:
        raise FileNotFoundError(
            f"Expected target image '{TARGET_FILENAME}' not found in '{image_dir}'."
        )

    excluded = PROBE_FILENAMES | {TARGET_FILENAME}
    irrelevant_files = [f for f in all_files if f not in excluded]
    if not irrelevant_files:
        raise ValueError(
            f"No irrelevant images found in '{image_dir}'. Add at least a "
            f"few neutral images besides your probe and target images."
        )

    return {
        "probes": [os.path.join(image_dir, f) for f in sorted(PROBE_FILENAMES)],
        "target": os.path.join(image_dir, TARGET_FILENAME),
        "irrelevant": [os.path.join(image_dir, f) for f in irrelevant_files],
    }


def build_trial_sequence(images):
    """
    One block = N_IRRELEVANT_PER_BLOCK irrelevants + 1 probe + 1 target.
    Probe images are rotated through round-robin across blocks (block 1 uses
    probes[0], block 2 uses probes[1], etc., wrapping around), so with
    enough blocks every probe image gets shown roughly the same number of
    times overall.

    Each trial in the returned sequence is (label, image_path, event_code):
      - label: human-readable string for console printing ("irrelevant",
        "target", or the probe's own filename e.g. "probe1.jpg")
      - image_path: full path to the image file to display
      - event_code: the exact LSL marker code to send for this trial. Probes
        each get their own unique code from PROBE_EVENT_CODES, so you can
        tell exactly which probe was shown when analyzing the recording
        afterward.
    """
    probes = images["probes"]
    sequence = []
    for block_idx in range(N_BLOCKS):
        n_pick = min(N_IRRELEVANT_PER_BLOCK, len(images["irrelevant"]))
        block_irrelevants = random.sample(images["irrelevant"], k=n_pick)
        for path in block_irrelevants:
            sequence.append(("irrelevant", path, EVENT_CODES["irrelevant"]))

        probe_path = probes[block_idx % len(probes)]
        probe_filename = os.path.basename(probe_path)
        sequence.append((probe_filename, probe_path, PROBE_EVENT_CODES[probe_filename]))

        sequence.append(("target", images["target"], EVENT_CODES["target"]))
    return sequence


def run_session():
    images = discover_images(IMAGE_DIR)
    print(f"Found {len(images['irrelevant'])} irrelevant images, "
          f"{len(images['probes'])} probe image(s), 1 target ({TARGET_FILENAME}).")
    print("Probe marker codes:")
    for filename, code in sorted(PROBE_EVENT_CODES.items()):
        print(f"  {filename}: code={code}")
    print(f"Other codes: irrelevant={EVENT_CODES['irrelevant']}, "
          f"target={EVENT_CODES['target']}, response={EVENT_CODES['response']}")

    outlet = create_marker_outlet()

    pygame.init()
    screen = pygame.display.set_mode(SCREEN_SIZE)
    pygame.display.set_caption("CIT Image Presentation")
    font = pygame.font.SysFont(None, 36)

    def show_blank():
        screen.fill(BACKGROUND_COLOR)
        pygame.display.flip()

    def show_message(text):
        screen.fill(BACKGROUND_COLOR)
        label = font.render(text, True, (255, 255, 255))
        rect = label.get_rect(center=(SCREEN_SIZE[0] // 2, SCREEN_SIZE[1] // 2))
        screen.blit(label, rect)
        pygame.display.flip()

    show_message("Press SPACE to begin")
    waiting = True
    while waiting:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                waiting = False

    sequence = build_trial_sequence(images)
    print(f"Running {len(sequence)} trials.")

    for label, image_path, event_code in sequence:
        img = pygame.image.load(image_path)
        img = pygame.transform.scale(img, SCREEN_SIZE)

        # --- Show the image AND send the marker at the same moment ---
        screen.blit(img, (0, 0))
        pygame.display.flip()
        send_marker(outlet, event_code)   # <-- marker fires here, right as the image appears

        is_probe = label in PROBE_EVENT_CODES
        print(f"[{'PROBE: ' + label if is_probe else label.upper()}] code={event_code}")

        # Watch for a response during target display (positive control)
        responded = False
        trial_start = time.time()
        while time.time() - trial_start < IMAGE_DURATION_S:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                    if label == "target" and not responded:
                        send_marker(outlet, EVENT_CODES["response"])
                        responded = True

        # --- Blank/ISI period ---
        show_blank()
        time.sleep(ISI_S)

    show_message("Session complete")
    time.sleep(2)
    pygame.quit()
    print("\nSession complete.")


if __name__ == "__main__":
    # Make sure to run: pip install pylsl pygame
    run_session()