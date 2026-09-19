"""Play the existing food-robot jingle and prerecorded vendor announcements."""

import argparse
from pathlib import Path
import random
import shutil
import signal
import subprocess
import time


DEFAULT_AUDIO = Path("/home/admin/food_robot/audio")


class AudioPlayer:
    """Own one playback process so music and speech never overlap."""

    def __init__(self, speaker):
        self.speaker = speaker
        self.process = None

    def stop(self):
        process = self.process
        if process is None:
            return
        try:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        finally:
            self.process = None

    def start(self, path):
        self.stop()
        if path.suffix.lower() == ".mp3":
            command = ["mpg123", "-q", "-o", "alsa", "-a", self.speaker, str(path)]
        else:
            command = ["aplay", "-q", "-D", self.speaker, str(path)]
        # Keep stderr visible: missing/disconnected audio devices must not fail silently.
        self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL)

    def play_clip(self, path):
        self.start(path)
        try:
            code = self.process.wait()
            if code:
                raise RuntimeError(f"Playback failed for {path.name} (exit {code}).")
        finally:
            self.stop()

    def play_music(self, path, duration):
        """Repeat short jingles until the next announcement is due."""
        deadline = time.monotonic() + duration
        try:
            while time.monotonic() < deadline:
                self.start(path)
                while time.monotonic() < deadline:
                    code = self.process.poll()
                    if code is not None:
                        if code:
                            raise RuntimeError(f"Music playback failed (exit {code}).")
                        break
                    time.sleep(min(0.05, max(0, deadline - time.monotonic())))
        finally:
            self.stop()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-dir", type=Path, default=DEFAULT_AUDIO)
    parser.add_argument("--speaker", default="plughw:0,0")
    parser.add_argument("--min-interval", type=float, default=7)
    parser.add_argument("--max-interval", type=float, default=7)
    args = parser.parse_args()
    if not (0 < args.min_interval <= args.max_interval < float("inf")):
        parser.error("Intervals must be finite and 0 < min-interval <= max-interval.")
    return args


def run(args):
    jingle = args.audio_dir / "jingle.wav"
    voice_dir = args.audio_dir / "voice"
    announcements = sorted(voice_dir.glob("vendor*.mp3"))
    announcements += sorted(voice_dir.glob("funny*.mp3"))
    if not jingle.is_file() or jingle.stat().st_size == 0:
        raise RuntimeError(f"Missing or empty jingle: {jingle}")
    if not announcements:
        raise RuntimeError(f"No vendor/funny MP3 clips found in {voice_dir}")
    for clip in announcements:
        if clip.stat().st_size == 0:
            raise RuntimeError(f"Empty announcement: {clip}")
    for executable in ("aplay", "mpg123"):
        if shutil.which(executable) is None:
            raise RuntimeError(f"Required audio player is unavailable: {executable}")

    player = AudioPlayer(args.speaker)
    previous = None
    try:
        while True:
            duration = random.uniform(args.min_interval, args.max_interval)
            print(f"Playing jingle for {duration:.0f} seconds...", flush=True)
            player.play_music(jingle, duration)
            choices = [clip for clip in announcements if clip != previous] or announcements
            clip = random.choice(choices)
            print(f"Announcement: {clip.name}", flush=True)
            player.play_clip(clip)
            previous = clip
    finally:
        player.stop()


def stop_requested(signum, frame):
    raise KeyboardInterrupt


def main():
    args = parse_args()
    signal.signal(signal.SIGTERM, stop_requested)
    try:
        run(args)
    except KeyboardInterrupt:
        print("\nVendor audio stopped.")
    except (OSError, RuntimeError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
