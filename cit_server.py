#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cit_server.py — lokaler Helfer fuer das P300-CIT-Webinterface.

Warum noetig: Ein Browser kann selbst KEIN LSL lesen und KEINE Python-Skripte
starten (pylsl/pygame sind nativ). Dieser kleine Server (nur Standardbibliothek)
laeuft auf DEINEM Rechner, liefert die Weboberflaeche aus und startet auf
Knopfdruck im Hintergrund:

    1) die Reizpraesentation  (lie_multiple_markers.py / cit_image_presentation.py)
       -> erzeugt den LSL-Marker-Stream "CIT_Markers" und zeigt die Bilder
    2) capture_lie.py
       -> nimmt Unicorn-EEG + Marker auf und schreibt die CSV (pro Zeile geflusht)

Voraussetzung / Projektstruktur (cit_server.py im Projekt-Wurzelverzeichnis):

    projekt/
    |- cit_server.py            <- diese Datei
    |- cit_lie_detector.html    <- die Weboberflaeche (gleicher Ordner)
    |- capture_lie.py
    |- lie_multiple_markers.py  (oder cit_image_presentation.py)
    |- utils/
    |   |- utils.py             (capture_lie importiert utils.utils)
    |- images/                  (wird vom Server aus den Uploads befuellt)
    |- data/eeg_recordings/     (wird bei Bedarf angelegt)
    |- data/eeg_raw_recordings/

Benutzung:
    1) Unicorn-LSL-Stream starten (g.tec Unicorn Recorder -> LSL).
    2) python cit_server.py
    3) Im Browser oeffnen:  http://127.0.0.1:8000
    4) Tab 1: Bilder hochladen/zuordnen. Tab 2: "EEG aufnehmen" -> im
       Praesentationsfenster LEERTASTE druecken -> "Stopp" -> CSV erscheint.

Optionen:
    python cit_server.py --port 8000 --presentation lie_multiple_markers.py \
                         --capture capture_lie.py --html cit_lie_detector.html
"""
import argparse
import base64
import glob
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp")

# ---------------------------------------------------------------------------
# Configuration resolved at startup (overridable via CLI)
# ---------------------------------------------------------------------------
CFG = {
    "port": 8000,
    "html": "cit_lie_detector.html",
    "capture": "capture_lie.py",
    "presentation": None,   # auto-detected if None
    "lead_seconds": 2.0,    # wait after presentation start before capture starts
}


def find_presentation():
    """Locate the stimulus script that creates the CIT_Markers LSL stream."""
    for cand in ("lie_multiple_markers.py", "cit_image_presentation.py"):
        if os.path.exists(os.path.join(HERE, cand)):
            return cand
    # fall back: scan for a file that builds the marker outlet
    for f in sorted(glob.glob(os.path.join(HERE, "*.py"))):
        base = os.path.basename(f)
        if base in (os.path.basename(__file__), CFG["capture"], "_cit_runtime_presentation.py"):
            continue
        try:
            txt = open(f, "r", encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        if "CIT_Markers" in txt and "StreamOutlet" in txt:
            return base
    return None


# ---------------------------------------------------------------------------
# Capture state (single session at a time)
# ---------------------------------------------------------------------------
class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.pres = None      # presentation Popen
        self.cap = None       # capture Popen
        self.start_ts = 0.0
        self.subject = None
        self.running = False
        self.last_csv_path = None

    def is_running(self):
        return self.running and self.cap is not None and self.cap.poll() is None

ST = State()


def ensure_dirs():
    for d in ("data/eeg_recordings", "data/eeg_raw_recordings", "images", "logs"):
        os.makedirs(os.path.join(HERE, d), exist_ok=True)


def clear_images():
    img_dir = os.path.join(HERE, "images")
    os.makedirs(img_dir, exist_ok=True)
    for f in os.listdir(img_dir):
        if f.lower().endswith(IMAGE_EXTS):
            try:
                os.remove(os.path.join(img_dir, f))
            except OSError:
                pass


def save_images(images):
    """
    images: list of {name, cat, data(dataURL)}.
    Writes them into images/ with the names the presentation expects:
      probes (sorted by original name)  -> probe1.JPG, probe2.JPG, ...
      target                            -> target.jpg
      irrelevant                        -> irrelevant_1.jpg, irrelevant_2.jpg, ...
    Returns the list of probe filenames actually written (for the runtime patch).
    """
    img_dir = os.path.join(HERE, "images")
    clear_images()

    def decode(data_url):
        if "," in data_url:
            data_url = data_url.split(",", 1)[1]
        return base64.b64decode(data_url)

    probes = sorted([im for im in images if im.get("cat") == "probe"],
                    key=lambda im: im.get("name", ""))
    targets = [im for im in images if im.get("cat") == "target"]
    irrels = [im for im in images if im.get("cat") == "irrelevant"]

    probe_names = []
    for i, im in enumerate(probes, start=1):
        fn = f"probe{i}.JPG"
        with open(os.path.join(img_dir, fn), "wb") as fh:
            fh.write(decode(im["data"]))
        probe_names.append(fn)

    if targets:
        with open(os.path.join(img_dir, "target.jpg"), "wb") as fh:
            fh.write(decode(targets[0]["data"]))

    for i, im in enumerate(irrels, start=1):
        with open(os.path.join(img_dir, f"irrelevant_{i}.jpg"), "wb") as fh:
            fh.write(decode(im["data"]))

    return probe_names


def write_runtime_presentation(probe_names):
    """
    Copy the user's presentation script and rewrite PROBE_FILENAMES /
    TARGET_FILENAME to match the images we just saved, so it works for any
    probe count without touching the original file. Returns the runtime path.
    """
    src_path = os.path.join(HERE, CFG["presentation"])
    src = open(src_path, "r", encoding="utf-8", errors="ignore").read()
    probe_set = "{" + ", ".join(f'"{n}"' for n in probe_names) + "}"
    src = re.sub(r"PROBE_FILENAMES\s*=\s*\{[^}]*\}",
                 "PROBE_FILENAMES = " + probe_set, src, count=1)
    src = re.sub(r'TARGET_FILENAME\s*=\s*["\'][^"\']*["\']',
                 'TARGET_FILENAME = "target.jpg"', src, count=1)
    out = os.path.join(HERE, "_cit_runtime_presentation.py")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(src)
    return out


def newest_prc_csv():
    pat = os.path.join(HERE, "data", "eeg_recordings", "**", "*_eeg_prc_log.csv")
    files = glob.glob(pat, recursive=True)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def start_capture(subject, images):
    with ST.lock:
        if ST.is_running():
            return False, "Aufnahme laeuft bereits."
        if not CFG["presentation"]:
            return False, "Kein Praesentationsskript gefunden (lie_multiple_markers.py / cit_image_presentation.py)."
        cap_path = os.path.join(HERE, CFG["capture"])
        if not os.path.exists(cap_path):
            return False, f"{CFG['capture']} nicht gefunden."

        ensure_dirs()
        probe_names = save_images(images or [])
        if not probe_names:
            return False, "Keine Sonden-Bilder erhalten."
        runtime_pres = write_runtime_presentation(probe_names)

        log_dir = os.path.join(HERE, "logs")
        pres_log = open(os.path.join(log_dir, "presentation.log"), "w")
        cap_log = open(os.path.join(log_dir, "capture.log"), "w")

        # 1) presentation first (creates the CIT_Markers outlet)
        ST.pres = subprocess.Popen([sys.executable, runtime_pres],
                                   cwd=HERE, stdout=pres_log, stderr=subprocess.STDOUT)
        time.sleep(CFG["lead_seconds"])

        # 2) capture, feeding the subject id to its input() prompt via stdin
        ST.cap = subprocess.Popen([sys.executable, cap_path],
                                  cwd=HERE, stdin=subprocess.PIPE,
                                  stdout=cap_log, stderr=subprocess.STDOUT, text=True)
        try:
            ST.cap.stdin.write(f"{int(subject)}\n")
            ST.cap.stdin.flush()
        except (BrokenPipeError, ValueError):
            pass

        ST.start_ts = time.time()
        ST.subject = int(subject)
        ST.running = True
        return True, "gestartet"


def _terminate(proc, use_sigint=False):
    if proc is None or proc.poll() is not None:
        return
    try:
        if use_sigint and os.name != "nt":
            proc.send_signal(signal.SIGINT)   # -> KeyboardInterrupt -> loggers close cleanly
        else:
            proc.terminate()
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass


def stop_capture():
    with ST.lock:
        if not ST.running:
            return False, "Es laeuft keine Aufnahme.", None
        # stop presentation (SIGTERM is fine) and capture (SIGINT for a clean close)
        _terminate(ST.pres, use_sigint=False)
        _terminate(ST.cap, use_sigint=True)
        # give the capture process a moment to flush/close; CSV is flushed per row anyway
        deadline = time.time() + 6
        while ST.cap is not None and ST.cap.poll() is None and time.time() < deadline:
            time.sleep(0.2)
        for p in (ST.cap, ST.pres):
            if p is not None and p.poll() is None:
                try:
                    p.kill()
                except Exception:
                    pass
        ST.running = False
        time.sleep(0.3)
        path = newest_prc_csv()
        ST.last_csv_path = path
        if not path or not os.path.exists(path):
            return False, "Keine CSV gefunden. Lief der Unicorn-LSL-Stream? (siehe logs/capture.log)", None
        try:
            text = open(path, "r", encoding="utf-8", errors="ignore").read()
        except OSError as e:
            return False, f"CSV-Lesefehler: {e}", None
        rows = max(0, text.count("\n") - 1)
        return True, "gestoppt", {"filename": os.path.basename(path), "rows": rows, "csv": text}


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "CITServer/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("  [http] " + (fmt % args) + "\n")

    def _send(self, code, body=b"", ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj), "application/json; charset=utf-8")

    def _read_json(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n <= 0:
            return {}
        raw = self.rfile.read(n)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _serve_html(self):
        path = os.path.join(HERE, CFG["html"])
        if not os.path.exists(path):
            self._send(404, f"{CFG['html']} nicht im selben Ordner wie cit_server.py gefunden.",
                       "text/plain; charset=utf-8")
            return
        with open(path, "rb") as fh:
            self._send(200, fh.read(), "text/html; charset=utf-8")

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p in ("/", "/index.html", "/" + CFG["html"]):
            self._serve_html()
        elif p == "/health":
            self._json({"ok": True, "presentation": CFG["presentation"], "capture": CFG["capture"]})
        elif p == "/capture/status":
            elapsed = int(time.time() - ST.start_ts) if ST.running else 0
            self._json({"running": ST.is_running(), "elapsed": elapsed, "subject": ST.subject})
        elif p == "/capture/csv":
            path = ST.last_csv_path or newest_prc_csv()
            if path and os.path.exists(path):
                with open(path, "rb") as fh:
                    self._send(200, fh.read(), "text/csv; charset=utf-8")
            else:
                self._send(404, "Keine CSV vorhanden.", "text/plain; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain; charset=utf-8")

    def do_POST(self):
        p = self.path.split("?", 1)[0]
        if p == "/capture/start":
            data = self._read_json()
            ok, msg = start_capture(data.get("subject", 1), data.get("images", []))
            if ok:
                self._json({"ok": True, "message": msg})
            else:
                self._send(409, msg, "text/plain; charset=utf-8")
        elif p == "/capture/stop":
            ok, msg, payload = stop_capture()
            if ok:
                self._json(payload)
            else:
                self._send(409, msg, "text/plain; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain; charset=utf-8")


def main():
    ap = argparse.ArgumentParser(description="Lokaler Helfer fuer das P300-CIT-Webinterface.")
    ap.add_argument("--port", type=int, default=CFG["port"])
    ap.add_argument("--html", default=CFG["html"])
    ap.add_argument("--capture", default=CFG["capture"])
    ap.add_argument("--presentation", default=None)
    ap.add_argument("--lead-seconds", type=float, default=CFG["lead_seconds"])
    args = ap.parse_args()

    CFG["port"] = args.port
    CFG["html"] = args.html
    CFG["capture"] = args.capture
    CFG["lead_seconds"] = args.lead_seconds
    CFG["presentation"] = args.presentation or find_presentation()

    ensure_dirs()
    print("=" * 64)
    print("  P300-CIT lokaler Server")
    print("  HTML        :", CFG["html"], "(" + ("gefunden" if os.path.exists(os.path.join(HERE, CFG["html"])) else "FEHLT!") + ")")
    print("  Capture     :", CFG["capture"], "(" + ("ok" if os.path.exists(os.path.join(HERE, CFG["capture"])) else "FEHLT!") + ")")
    print("  Praesentation:", CFG["presentation"] or "NICHT GEFUNDEN")
    print("  Hinweis     : Unicorn-LSL-Stream muss laufen, bevor du aufnimmst.")
    print("-" * 64)
    print(f"  Im Browser oeffnen:  http://127.0.0.1:{CFG['port']}")
    print("  Beenden: Strg+C")
    print("=" * 64)

    httpd = ThreadingHTTPServer(("127.0.0.1", CFG["port"]), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer beendet.")
        if ST.running:
            stop_capture()


if __name__ == "__main__":
    main()
