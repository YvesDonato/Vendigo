from dataclasses import dataclass
import random


@dataclass(frozen=True)
class Phrase:
    category: str
    id: str
    text: str


LINES = {
    "roaming": [
        "Snacks on the move! Come grab something!",
        "Come on over! I brought the store to you!",
        "Hungry? Good. I happen to know a guy.",
        "Come get your snacks before I roll away!",
        "You bring the appetite. I'll handle the driving.",
        "Snacks right here! Zero walking required!",
    ],
    "funny": [
        "Cold drinks, good snacks, questionable driving!",
        "Hey, I drove all this way. At least take a look!",
        "Food delivery? Nah. The whole store showed up.",
        "Why walk to the vending machine when the vending machine comes to you?",
        "Look at me! A vending machine with a driver's license!",
        "Beep beep! Important snack business coming through!",
    ],
    "greeting": ["Hey there! Your snack guide has arrived.", "Well, look who found the snack wagon!"],
    "question": ["Fancy a snack?", "Can I tempt you with a snack break?"],
    "yes": [
        "Now we're talking! Scan the QR code and pick your snack.",
        "That's what I like to hear! Scan the QR code and pick what you want.",
        "Excellent choice. Scan right here and pick what looks good.",
        "Now we're in business! Scan the QR code and grab whatever looks good.",
    ],
    "no": [
        "Aw, you're breaking my heart! Alright, have a good one!",
        "Can't win 'em all! Catch you later!",
        "All good! I'll keep rolling. Have a great day!",
        "No problem! I'll be around if you change your mind.",
    ],
    # This category deliberately makes no claim that a payment was received.
    "payment": ["The QR code has the next step. Take your time!", "Scan right here when you're ready."],
    "goodbye": ["You got it. I'll be around.", "Catch you later! Stay snacky."],
    "wake": ["Hey! What can your snack guide do for you?", "You rang? What's on your mind?"],
    "repeat": ["Didn't catch that. Was that a yes or a no?", "One more time for me: yes or no?"],
    "errors": ["Give me one second, my brain hit a pothole.", "Didn't catch that. Try me again."],
}


class PhraseManager:
    def __init__(self, rng=None, funny_probability=0.12):
        self.rng = rng or random.Random()
        self.funny_probability = funny_probability
        self.phrases = {category: [Phrase(category, f"{i + 1:02d}", text) for i, text in enumerate(lines)]
                        for category, lines in LINES.items()}
        self.previous = {}
        self.last_text = None

    def choose(self, category):
        candidates = [p for p in self.phrases[category]
                      if p.text != self.previous.get(category) and p.text != self.last_text]
        phrase = self.rng.choice(candidates or self.phrases[category])
        self.previous[category] = self.last_text = phrase.text
        return phrase

    def sales_line(self):
        return self.choose("funny" if self.rng.random() < self.funny_probability else "roaming")

    def all(self):
        return [phrase for phrases in self.phrases.values() for phrase in phrases]
