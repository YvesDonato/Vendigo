"""Temporary transcript-based wake detector; swap for a local keyword engine later."""

import time
from typing import Protocol

from vendi.speech.yes_no import normalize


class WakeWordDetector(Protocol):
    def detect(self, transcript: str) -> bool: ...


class TranscriptWakeWord:
    def __init__(self, cooldown=5, clock=time.monotonic):
        self.cooldown = cooldown
        self.clock = clock
        self.last_trigger = float("-inf")

    def detect(self, transcript):
        # Whole utterance only. Quoted mentions and fuzzy near-matches are not triggers.
        if " ".join(normalize(transcript).split()) != "hey vendi":
            return False
        now = self.clock()
        if now - self.last_trigger < self.cooldown:
            return False
        self.last_trigger = now
        return True
