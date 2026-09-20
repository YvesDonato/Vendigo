"""Silence before speech is different from an unfinished customer utterance."""

from array import array
import math
import sys
import time

from vendi.errors import VoiceFailure
from vendi.speech.yes_no import normalize


HESITATIONS = {"um", "uh", "uhm", "erm", "hmm", "hm", "so", "well", "wait", "hold on",
               "hang on", "one second", "give me a second", "let me think", "let me see", "okay so"}


def is_hesitation(text):
    words = normalize(text).split()
    return " ".join(words) in HESITATIONS or (bool(words) and all(word in {"um", "uh", "erm", "hmm"} for word in words))


def pcm_rms(data):
    samples = array("h")
    samples.frombytes(data)
    if sys.byteorder != "little":
        samples.byteswap()
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples)) if samples else 0


class TurnProgress:
    """Energy extends listening only; the recognizer still decides what counts as speech."""

    def __init__(self, idle_timeout, max_utterance, threshold=250, on_activity=lambda: None, clock=time.monotonic):
        self.clock = clock
        self.started = clock()
        self.idle_timeout = idle_timeout
        self.max_utterance = max_utterance
        self.threshold = threshold
        self.on_activity = on_activity
        self.first_speech = None
        self.last_speech = None
        self.last_audio_speech = None
        self.audio_revision = 0
        self.last_partial = ""
        self.voiced_seconds = 0

    def speech(self):
        now = self.clock()
        if self.first_speech is None:
            self.first_speech = now
        self.last_speech = now
        self.on_activity()

    def audio(self, data, rate=16000):
        if pcm_rms(data) >= self.threshold:
            self.voiced_seconds += len(data) / (rate * 2)
            if self.voiced_seconds >= 0.08:
                self.last_audio_speech = self.clock()
                self.audio_revision += 1
                self.speech()
        else:
            self.voiced_seconds = 0

    def partial(self, text):
        if text.strip() and text != self.last_partial:
            self.last_partial = text
            self.speech()

    def expired(self):
        now = self.clock()
        if self.first_speech is None:
            return now - self.started >= self.idle_timeout
        if now - self.first_speech >= self.max_utterance:
            # Never silently send a truncated utterance to GPT.
            raise VoiceFailure("stt", "That turn was too long or unclear. Try a shorter sentence.")
        return False
