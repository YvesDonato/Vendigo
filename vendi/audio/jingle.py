"""Tiny original synthesized placeholder; no downloaded or copyrighted melody."""

import math
import struct
import wave


def ensure_jingle(config):
    if config.jingle_path.is_file():
        return config.jingle_path
    path = config.cache_dir / "original-jingle.wav"
    if path.is_file():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 24000
    notes = (392, 523.25, 440, 659.25, 587.33, 440, 493.88, 392)
    with wave.open(str(path), "wb") as audio:
        audio.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        for frequency in notes:
            count = int(rate * 0.32)
            for i in range(count):
                envelope = min(1, i / (rate * 0.015)) * max(0, 1 - i / count) ** 2
                value = int(5000 * envelope * math.sin(2 * math.pi * frequency * i / rate))
                audio.writeframesraw(struct.pack("<h", value))
    return path
