"""Speech-only pronunciation; written replies and conversation history stay intact."""

import re

from vendi.speech.spoken_prices import spoken_prices


def speech_text(text):
    return re.sub(r"\bvendigo\b", "vend-ee-go", spoken_prices(text), flags=re.IGNORECASE)
