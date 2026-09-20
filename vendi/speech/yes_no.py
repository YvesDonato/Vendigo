"""Conservative purchase consent classification; never sends text to an LLM."""

from enum import Enum
import re


class YesNo(str, Enum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"


def normalize(text):
    return re.sub(r"[^a-z0-9\s]", "", text.lower().replace("’", "'")).strip()


YES = {"yes", "yeah", "yep", "yup", "sure", "okay", "ok", "absolutely", "sounds good",
       "yes please", "yeah please", "sure thing", "of course", "lets do it", "id like to", "why not"}
NO = {"no", "nope", "nah", "no thanks", "no thank you", "not today", "im good", "i am good",
      "im okay", "im ok", "no im good", "not now", "maybe later", "no thank you im good"}


def classify_yes_no(transcript: str) -> YesNo:
    text = " ".join(normalize(transcript).split())
    if text in NO:
        return YesNo.NO
    if text in YES:
        return YesNo.YES
    # Do not accept substrings: "not sure", "yes or no", "yeah no" remain UNKNOWN.
    if text.endswith(" thanks") and text[:-7] in YES:
        return YesNo.YES
    return YesNo.UNKNOWN
